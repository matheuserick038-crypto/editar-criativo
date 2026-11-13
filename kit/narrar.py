#!/usr/bin/env python3
"""Gera a narração (hook + body) de cada criativo de um lote, com tempo por palavra.

Uso: python narrar.py <oferta>/07_roteiros/lote_01.json [--ids c01,c02] [--refazer]

Motores (lote["narracao"]["motor"]):
  edge       vozes neurais grátis (Microsoft Edge TTS) — padrão
  eleven     ElevenLabs (ELEVENLABS_API_KEY em ~/.config/editar-criativo/.env)
  existente  usa 05_audios/<id>.mp3 já gravado e transcreve com Whisper local
Saídas: 05_audios/<id>.mp3 e 05_audios/<id>.palavras.json
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from comum import (EXT_AUDIO, config, configurar_saida, duracao, ffmpeg, gravar_json, ler_json,
                   log, pasta_oferta)
from transcrever import transcrever

VOZ_EDGE_PADRAO = "pt-BR-AntonioNeural"
VOZ_ELEVEN_PADRAO = "pNInz6obpgDQGcFmaJgB"  # "Adam" — troque pelo voice_id da sua conta
PAUSA_HOOK_BODY = 0.18


# ---------------------------------------------------------------- edge-tts
async def _edge(texto: str, voz: str, velocidade: str, destino: Path) -> list[dict]:
    import edge_tts  # noqa: PLC0415

    com = edge_tts.Communicate(texto, voz, rate=velocidade, boundary="WordBoundary")
    palavras = []
    with open(destino, "wb") as f:
        async for bloco in com.stream():
            if bloco["type"] == "audio":
                f.write(bloco["data"])
            elif bloco["type"] == "WordBoundary":
                ini = bloco["offset"] / 1e7
                palavras.append({"t": bloco["text"], "ini": round(ini, 3),
                                 "fim": round(ini + bloco["duration"] / 1e7, 3)})
    return palavras


def _norm(p: str) -> str:
    return re.sub(r"[^\w]", "", p.lower())


def pontuar(palavras: list[dict], texto: str) -> list[dict]:
    """O edge-tts devolve as palavras sem pontuação; recoloca a do roteiro (a legenda quebra em . ? !)."""
    tokens = texto.split()
    j = 0
    for p in palavras:
        alvo = _norm(p["t"])
        for k in range(j, min(j + 4, len(tokens))):
            if _norm(tokens[k]) == alvo:
                p["t"], j = tokens[k], k + 1
                break
    return palavras


def tts_edge(texto: str, destino: Path, voz: str, velocidade: str, tentativas: int = 5) -> list[dict]:
    """O serviço grátis falha de forma intermitente (NoAudioReceived): tenta de novo com espera crescente."""
    ultimo = None
    for n in range(1, tentativas + 1):
        try:
            palavras = asyncio.run(_edge(texto, voz, velocidade, destino))
            if palavras and destino.stat().st_size > 0:
                return pontuar(palavras, texto)
            ultimo = "resposta sem áudio ou sem tempos de palavra"
        except Exception as erro:  # noqa: BLE001 — erros de rede/serviço do edge-tts
            ultimo = f"{type(erro).__name__}: {erro}"
        if n < tentativas:
            log(f"voz grátis falhou (tentativa {n}/{tentativas}), tentando de novo…")
            time.sleep(1.5 * n)
    raise SystemExit(f"Voz grátis indisponível após {tentativas} tentativas ({voz}): {ultimo}. "
                     "Verifique a internet ou troque de voz/motor.")


# ---------------------------------------------------------------- ElevenLabs
def tts_eleven(texto: str, destino: Path, voz: str, modelo: str) -> list[dict]:
    chave = config("ELEVENLABS_API_KEY")
    if not chave:
        raise SystemExit("Falta ELEVENLABS_API_KEY em ~/.config/editar-criativo/.env")
    corpo = json.dumps({"text": texto, "model_id": modelo,
                        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8}}).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voz}/with-timestamps?output_format=mp3_44100_128",
        data=corpo, headers={"xi-api-key": chave, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            dados = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ElevenLabs recusou ({e.code}): {e.read()[:400]!r}") from None
    destino.write_bytes(base64.b64decode(dados["audio_base64"]))
    al = dados.get("alignment") or dados.get("normalized_alignment") or {}
    chars = al.get("characters", [])
    inis = al.get("character_start_times_seconds", [])
    fins = al.get("character_end_times_seconds", [])
    palavras, atual, ini, fim = [], "", None, None
    for c, a, b in zip(chars, inis, fins):
        if c.isspace():
            if atual:
                palavras.append({"t": atual, "ini": round(ini, 3), "fim": round(fim, 3)})
            atual, ini = "", None
            continue
        if ini is None:
            ini = a
        atual += c
        fim = b
    if atual:
        palavras.append({"t": atual, "ini": round(ini, 3), "fim": round(fim, 3)})
    return palavras


# ---------------------------------------------------------------- orquestração
def _sintetizar(motor: str, texto: str, destino: Path, ajustes: dict) -> list[dict]:
    if motor == "edge":
        return tts_edge(texto, destino, ajustes.get("voz") or VOZ_EDGE_PADRAO, ajustes.get("velocidade", "+8%"))
    if motor == "eleven":
        return tts_eleven(texto, destino, ajustes.get("voz") or config("ELEVENLABS_VOICE_ID", VOZ_ELEVEN_PADRAO),
                          ajustes.get("modelo", "eleven_multilingual_v2"))
    raise SystemExit(f"Motor desconhecido: {motor}")


def _limpar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip())


def narrar_criativo(oferta: Path, criativo: dict, ajustes: dict, refazer: bool) -> dict:
    cid = criativo["id"]
    audios = oferta / "05_audios"
    work = oferta / "_work" / cid
    work.mkdir(parents=True, exist_ok=True)
    final = audios / f"{cid}.mp3"
    meta_path = audios / f"{cid}.palavras.json"
    motor = criativo.get("motor") or ajustes.get("motor", "edge")
    aj = {**ajustes, **{k: criativo[k] for k in ("voz", "velocidade") if k in criativo}}

    if meta_path.exists() and final.exists() and not refazer:
        log(f"{cid}: narração já existe (use --refazer para gerar de novo)")
        return ler_json(meta_path)

    if motor == "existente":
        existente = next((audios / f"{cid}{ext}" for ext in sorted(EXT_AUDIO) if (audios / f"{cid}{ext}").exists()), None)
        if not existente:
            raise SystemExit(f"{cid}: coloque o áudio em 05_audios/{cid}.mp3")
        if existente.suffix.lower() != ".mp3":
            ffmpeg("-i", existente, "-ac", "1", "-ar", "44100", "-b:a", "160k", final)
        palavras = transcrever(final, work / "palavras_whisper.json")["palavras"]
        n_hook = len(_limpar(criativo.get("hook")).split())
        fim_hook = criativo.get("gancho_duracao") or (palavras[n_hook - 1]["fim"] if 0 < n_hook <= len(palavras) else 3.0)
        meta = {"palavras": palavras, "fim_hook": round(float(fim_hook), 3), "duracao": round(duracao(final), 3)}
        gravar_json(meta_path, meta)
        return meta

    hook, body = _limpar(criativo.get("hook")), _limpar(criativo.get("body"))
    if not hook and not body:
        raise SystemExit(f"{cid}: roteiro sem 'hook' nem 'body'")
    partes, palavras, deslocamento = [], [], 0.0
    fim_hook = 0.0
    for nome, texto in (("hook", hook), ("body", body)):
        if not texto:
            continue
        arq = work / f"narr_{nome}.mp3"
        pals = _sintetizar(motor, texto, arq, aj)
        dur = duracao(arq)
        for p in pals:
            palavras.append({"t": p["t"], "ini": round(p["ini"] + deslocamento, 3), "fim": round(p["fim"] + deslocamento, 3)})
        partes.append(arq)
        if nome == "hook":
            fim_hook = dur
        deslocamento += dur + PAUSA_HOOK_BODY
    if len(partes) == 1:
        ffmpeg("-i", partes[0], "-ac", "1", "-ar", "44100", "-b:a", "160k", final)
    else:
        ffmpeg("-i", partes[0], "-i", partes[1], "-filter_complex",
               f"[0:a]apad=pad_dur={PAUSA_HOOK_BODY}[a0];[a0][1:a]concat=n=2:v=0:a=1[a]",
               "-map", "[a]", "-ac", "1", "-ar", "44100", "-b:a", "160k", final)
    if criativo.get("gancho_duracao"):
        fim_hook = float(criativo["gancho_duracao"])
    meta = {"palavras": palavras, "fim_hook": round(fim_hook, 3), "duracao": round(duracao(final), 3), "motor": motor}
    gravar_json(meta_path, meta)
    log(f"{cid}: narração {meta['duracao']:.1f}s ({motor}, {len(palavras)} palavras)")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lote")
    ap.add_argument("--ids", help="lista separada por vírgula")
    ap.add_argument("--refazer", action="store_true")
    a = ap.parse_args()
    lote = ler_json(Path(a.lote))
    oferta = pasta_oferta(Path(a.lote))
    ajustes = lote.get("narracao", {"motor": "edge"})
    filtro = set(a.ids.split(",")) if a.ids else None
    for criativo in lote["criativos"]:
        if filtro and criativo["id"] not in filtro:
            continue
        narrar_criativo(oferta, criativo, ajustes, a.refazer)


if __name__ == "__main__":
    configurar_saida()
    main()
