#!/usr/bin/env python3
"""Monta os criativos de um lote: b-roll cortado no ritmo da fala, faixa de gancho,
legenda palavra-a-palavra, efeitos sonoros e trilha. Saída 1080x1920 em 01_prontos/.

Uso: python montar.py <oferta>/07_roteiros/lote_01.json [--ids c01,c02] [--sem-narrar]
(Por padrão, chama narrar.py antes para quem ainda não tem narração.)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from comum import (ALTURA, EXT_IMAGEM, FPS, LARGURA, binario, configurar_saida, duracao, ffmpeg, ler_json,
                   listar_midias, log, pasta_oferta, resolver, tem_audio)
from legendas import (ALTURA_CANVAS_LEGENDA, cor_rgba, render_cartao, render_faixa, render_rotulo,
                      trilha_legendas)
from narrar import narrar_criativo

LINHA = 12                       # espessura da linha vermelha (par: cada metade precisa de altura par)
META_ALTURA = (ALTURA - LINHA) // 2
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


def _semente(*partes) -> int:
    return int(hashlib.md5("|".join(map(str, partes)).encode()).hexdigest()[:8], 16)


# ---------------------------------------------------------------- trilha visual
def _pedaco(src: Path, dur: float, w: int, h: int, destino: Path, rnd: random.Random,
            encaixe: str = "corte") -> None:
    quadros = max(int(round(dur * FPS)), 1)
    if src.suffix.lower() in EXT_IMAGEM:
        zoom_in = rnd.random() < 0.6
        z = f"min(1+0.10*on/{quadros},1.10)" if zoom_in else f"max(1.10-0.10*on/{quadros},1.0)"
        vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={quadros}:s={w}x{h}:fps={FPS},setsar=1")
        ffmpeg("-i", src, "-vf", vf, "-frames:v", quadros, *X264, "-an", destino)
        return
    total = duracao(src)
    entrada = []
    if total < dur + 0.1:
        entrada = ["-stream_loop", "-1"]
        inicio = 0.0
    else:
        inicio = rnd.uniform(0, max(0.0, total - dur - 0.05))
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},setsar=1"
    sw, sh = _dimensoes(src)
    if encaixe == "desfoque" and sw and sh and sw / sh > 1.1 and w / h < 0.8:
        # vídeo horizontal em tela vertical: o recorte central perde o exercício. Mostra uma faixa larga
        # (metade da altura) sobre o próprio vídeo desfocado.
        fh = (h // 2) // 2 * 2
        vf = (f"fps={FPS},split[a][b];"
              f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=24:2,eq=brightness=-0.10[bg];"
              f"[b]scale=-2:{fh},crop={w}:{fh}[fg];[bg][fg]overlay=0:(H-h)/2,setsar=1")
    ffmpeg(*entrada, "-ss", f"{inicio:.3f}", "-i", src, "-t", f"{dur:.3f}", "-vf", vf,
           "-frames:v", quadros, *X264, "-an", destino)


def _dimensoes(src: Path) -> tuple[int, int]:
    r = subprocess.run([binario("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0:s=x", str(src)], capture_output=True, text=True)
    try:
        a, b = r.stdout.strip().split("x")[:2]
        return int(a), int(b)
    except ValueError:
        return 0, 0


def _cortes(dur_total: float, palavras: list[dict], ritmo: float) -> list[float]:
    """Instantes de corte a cada ~ritmo s, puxados para o início da palavra mais próxima."""
    inicios = [p["ini"] for p in palavras]
    cortes, t = [0.0], ritmo
    while t < dur_total - 0.6:
        perto = min(inicios, key=lambda x: abs(x - t)) if inicios else t
        alvo = perto if abs(perto - t) < 0.5 and perto - cortes[-1] > 0.8 else t
        cortes.append(round(alvo, 3))
        t = alvo + ritmo
    return cortes


def _bordas(dur: float, forcados: list[float]) -> list[float]:
    bordas = [0.0]
    for t in sorted(forcados):
        if 0.8 < t < dur - 0.8 and t - bordas[-1] >= 0.7:
            bordas.append(round(t, 3))
    return bordas


def _cortes_em_secoes(dur: float, palavras: list[dict], ritmo: float, forcados: list[float]) -> list[float]:
    """Cortes obrigatórios viram bordas de seção (os colados a menos de 0,7 s se fundem no primeiro);
    dentro de cada seção, corta a cada ~ritmo s puxando para o início da palavra mais próxima."""
    bordas = _bordas(dur, forcados)
    inicios = [p["ini"] for p in palavras]
    cortes = []
    for a, b in zip(bordas, bordas[1:] + [dur]):
        cortes.append(a)
        t = a + ritmo
        while t < b - 0.6:
            perto = min(inicios, key=lambda x: abs(x - t)) if inicios else t
            alvo = perto if abs(perto - t) < 0.5 and perto - cortes[-1] > 0.8 and perto < b - 0.6 else t
            cortes.append(round(alvo, 3))
            t = alvo + ritmo
    return sorted(set(cortes))


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _resolver_textos(itens: list[dict], palavras: list[dict], fim_h: float, dur: float) -> list[dict]:
    """Converte 'desde'/'ate' (segundos, 'fim_hook', 'fim', 'proximo', 'palavra:X') em instantes."""
    normal = [re.sub(r"[^\w]", "", _sem_acento(p["t"])) for p in palavras]
    cursor = 0

    def achar(alvo: str, a_partir: float | None = None) -> float | None:
        """'desde' avança em ordem pela narração; 'ate' procura a partir do início do próprio texto."""
        nonlocal cursor
        a = re.sub(r"[^\w]", "", _sem_acento(alvo))
        inicio = cursor if a_partir is None else next(
            (i for i, p in enumerate(palavras) if p["ini"] > a_partir + 0.01), len(palavras))
        for i in range(inicio, len(palavras)):
            if normal[i] == a:
                if a_partir is None:
                    cursor = i + 1
                return float(palavras[i]["ini"])
        return None

    def tempo(v, padrao: float, a_partir: float | None = None) -> float:
        if v is None:
            return padrao
        if isinstance(v, (int, float)):
            return float(v)
        if v == "fim_hook":
            return fim_h
        if v == "fim":
            return dur
        if isinstance(v, str) and v.startswith("palavra:"):
            achado = achar(v.split(":", 1)[1], a_partir)
            if achado is None:
                log(f"aviso: palavra não encontrada na narração: {v}")
            return achado if achado is not None else padrao
        return padrao

    saida = []
    for it in itens:
        desde = it.get("desde", 0)
        ini = tempo(desde, 0.0)
        saida.append({**it, "ini": ini, "_ate": it.get("ate", "proximo" if str(desde).startswith("palavra:") else "fim"),
                      "cortar": it.get("cortar", str(desde).startswith("palavra:"))})
    for i, tx in enumerate(saida):
        # "próximo" = o próximo texto ancorado em palavra que começa depois deste (rodapés fixos não contam)
        prox = next((s["ini"] for s in saida[i + 1:]
                     if str(s.get("desde", "")).startswith("palavra:") and s["ini"] > tx["ini"] + 0.01), dur)
        if tx["_ate"] == "proximo":
            tx["fim"] = prox
        else:
            fim = tempo(tx["_ate"], dur, tx["ini"])
            # item de lista (ancorado em palavra) nunca invade o próximo; texto fixo vai até onde pediu
            tx["fim"] = min(fim, prox) if str(tx.get("desde", "")).startswith("palavra:") and prox > tx["ini"] else fim
    return saida


def trilha(midias: list[Path], cortes: list[float], dur_total: float, w: int, h: int,
           pasta: Path, semente: int, embaralhar: bool = True, encaixe: str = "corte") -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(semente)
    fila = list(midias)
    if embaralhar:
        rnd.shuffle(fila)
    pedacos = []
    for i, ini in enumerate(cortes):
        fim = cortes[i + 1] if i + 1 < len(cortes) else dur_total
        src = fila[i % len(fila)]
        destino = pasta / f"p{i:03d}.mp4"
        _pedaco(src, fim - ini, w, h, destino, rnd, encaixe)
        pedacos.append(destino)
    lista = pasta / "pedacos.txt"
    lista.write_text("".join(f"file '{p.as_posix()}'\n" for p in pedacos), encoding="utf-8")
    saida = pasta / "trilha.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", saida)
    return saida


# ---------------------------------------------------------------- composição
def _midias_do_criativo(oferta: Path, criativo: dict, chave: str, reserva: list[Path]) -> list[Path]:
    if criativo.get(chave):
        arqs = [resolver(oferta, m) for m in criativo[chave]]
        faltando = [str(a) for a in arqs if not a.exists()]
        if faltando:
            raise SystemExit(f"{criativo['id']}: mídia não encontrada: {faltando}")
        return arqs
    return reserva


def compor(oferta: Path, criativo: dict, estilo: str, narr: Path, meta: dict, saida: Path,
           pasta: Path, dur_total: float | None = None) -> None:
    cid = criativo["id"]
    layout = criativo.get("layout", "dividida")
    dur = dur_total or (meta["duracao"] + 0.35)
    palavras = meta["palavras"]
    todas = listar_midias(oferta)
    if not todas and not criativo.get("midias"):
        raise SystemExit("Nenhuma mídia em 02_brutos / 04_imagens / 03_apresentadora. Adicione vídeos ou imagens.")
    rnd = random.Random(_semente(cid, "midias"))
    embaralhadas = list(todas)
    rnd.shuffle(embaralhadas)
    # cortes obrigatórios: fim do hook (troca de imagem junto com a saída da faixa de gancho) e cada texto
    # ancorado em palavra (ex.: "TESTE 1" na palavra "primeiro"). Eles dividem o vídeo em seções; o ritmo
    # corta só dentro de cada seção, sem criar pedaços minúsculos colados nos obrigatórios.
    fim_h = float(meta.get("fim_hook") or 0)
    textos = _resolver_textos(criativo.get("textos") or [], palavras, fim_h, dur)
    forcados = [fim_h] + [tx["ini"] for tx in textos if tx["cortar"]]
    cortes = _cortes_em_secoes(dur, palavras, float(criativo.get("ritmo", 2.2)), forcados)

    if layout == "dividida":
        meio = max(1, len(embaralhadas) // 2)
        cima = _midias_do_criativo(oferta, criativo, "midias", embaralhadas[:meio] or embaralhadas)
        baixo = _midias_do_criativo(oferta, criativo, "midias_baixo", embaralhadas[meio:] or embaralhadas)
        t1 = trilha(cima, cortes, dur, LARGURA, META_ALTURA, pasta / "cima", _semente(cid, "cima"),
                    embaralhar=not criativo.get("midias"))
        t2 = trilha(baixo, cortes, dur, LARGURA, META_ALTURA, pasta / "baixo", _semente(cid, "baixo"),
                    embaralhar=not criativo.get("midias_baixo"))
        base = pasta / "base.mp4"
        ffmpeg("-i", t1, "-i", t2, "-filter_complex",
               f"color=c=0xE11D2A:s={LARGURA}x{LINHA}:r={FPS}:d={dur:.3f}[l];[0:v][l][1:v]vstack=inputs=3,setsar=1[v]",
               "-map", "[v]", "-t", f"{dur:.3f}", *X264, base)
        y_faixa = "(H-h)/2"
        y_leg = int(ALTURA * 0.76 - ALTURA_CANVAS_LEGENDA / 2)
    else:
        midias = _midias_do_criativo(oferta, criativo, "midias", embaralhadas)
        embaralhar = not criativo.get("midias")
        if criativo.get("midias_gancho"):
            # imagens só do gancho (ex.: moedas, esqueleto) não voltam no corpo do vídeo
            gancho_m = _midias_do_criativo(oferta, criativo, "midias_gancho", [])
            fim_h = float(meta.get("fim_hook") or 0)
            seq, g, b = [], 0, 0
            for ini in cortes:
                if ini < fim_h - 0.05:
                    seq.append(gancho_m[g % len(gancho_m)])
                    g += 1
                else:
                    seq.append(midias[b % len(midias)])
                    b += 1
            midias, embaralhar = seq, False
        secoes = [tx for tx in textos if tx.get("midias") and tx["cortar"]]
        if secoes:
            # textos com "midias" próprias: os cortes daquela seção usam só essas mídias (ex.: cada item da lista)
            base_seq = midias if not embaralhar else list(midias)
            bordas = _bordas(dur, forcados)
            seq, usados = [], {}
            for i, c in enumerate(cortes):
                ini_secao = max(b for b in bordas if b <= c + 0.01)
                dono = next((tx for tx in secoes if abs(tx["ini"] - ini_secao) < 0.75), None)
                if dono:
                    lst = [resolver(oferta, m) for m in dono["midias"]]
                    k = usados.get(id(dono), 0)
                    seq.append(lst[k % len(lst)])
                    usados[id(dono)] = k + 1
                else:
                    seq.append(base_seq[i % len(base_seq)])
            midias, embaralhar = seq, False
        base = trilha(midias, cortes, dur, LARGURA, ALTURA, pasta / "cheia", _semente(cid, "cheia"),
                      embaralhar=embaralhar, encaixe=criativo.get("encaixe", "corte"))
        y_faixa = str(int(ALTURA * 0.14))
        y_leg = int(ALTURA * 0.66 - ALTURA_CANVAS_LEGENDA / 2)

    leg = trilha_legendas(palavras, estilo, dur, pasta / "legendas")
    entradas = ["-i", base, "-i", narr, "-f", "concat", "-safe", "0", "-i", leg]
    filtros = [f"[2:v]fps={FPS},format=rgba[leg]"]
    atual, idx = "[0:v]", 3

    # fechamento: imagem/vídeo do produto em tela cheia nos últimos segundos (fundo desfocado + centro inteiro)
    t_fech = None
    if criativo.get("fechamento"):
        fech = resolver(oferta, criativo["fechamento"])
        if not fech.exists():
            raise SystemExit(f"{cid}: fechamento não encontrado: {fech}")
        seg = float(criativo.get("fechamento_seg", 3.2))
        t_fech = max(dur - seg, 0.5)
        if fech.suffix.lower() in EXT_IMAGEM:
            entradas += ["-loop", "1", "-t", f"{dur:.3f}", "-i", fech]
        else:
            entradas += ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", fech]
        filtros.append(
            f"[{idx}:v]fps={FPS},split[fa][fb];"
            f"[fa]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,crop={LARGURA}:{ALTURA},boxblur=28:2,"
            f"eq=brightness=-0.12[fbg];"
            f"[fb]scale={LARGURA - 80}:{ALTURA - 360}:force_original_aspect_ratio=decrease[ffg];"
            f"[fbg][ffg]overlay=(W-w)/2:(H-h)/2+60,setsar=1[fech];"
            f"{atual}[fech]overlay=0:0:enable='gte(t,{t_fech:.3f})':eof_action=pass[vf]")
        atual, idx = "[vf]", idx + 1

    gancho = (criativo.get("gancho_tela") or criativo.get("hook") or "").strip()
    fim_gancho = max(float(meta.get("fim_hook") or 0), 1.5)
    if gancho and criativo.get("gancho_tela") is not False:
        png = pasta / "gancho.png"
        y_g = y_faixa
        if criativo.get("gancho_estilo") == "pergunta":
            # cartão branco de "pergunta frequente" no lugar da faixa vermelha
            render_cartao(gancho, png, titulo=criativo.get("gancho_titulo", "PERGUNTA FREQUENTE"))
            y_g = str(int(ALTURA * 0.17)) if layout != "dividida" else "(H-h)/2"
        else:
            render_faixa(gancho, png)
        entradas += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
        filtros.append(f"{atual}[{idx}:v]overlay=(W-w)/2:{y_g}:enable='between(t,0,{fim_gancho:.3f})'[vg]")
        atual, idx = "[vg]", idx + 1
    if criativo.get("cta_tela"):
        png = pasta / "cta.png"
        render_faixa(criativo["cta_tela"], png, cor=(22, 163, 74, 255))
        entradas += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
        y_cta = str(int(ALTURA * 0.045)) if t_fech is not None else y_faixa  # no fechamento, topo livre
        ini_cta = t_fech if t_fech is not None else max(dur - 3.0, fim_gancho)
        filtros.append(f"{atual}[{idx}:v]overlay=(W-w)/2:{y_cta}:enable='gte(t,{ini_cta:.3f})'[vc]")
        atual, idx = "[vc]", idx + 1

    # faixa fixa (ex.: nome do produto + preço) do fim do gancho até o fim — modelada de criativo validado
    fixa = criativo.get("faixa_fixa")
    if fixa:
        png = pasta / "faixa_fixa.png"
        render_faixa(fixa["texto"], png, cor=cor_rgba(fixa.get("cor"), (249, 115, 22, 255)),
                     cor_texto=cor_rgba(fixa.get("cor_texto"), (17, 17, 17, 255)),
                     caixa_alta=bool(fixa.get("caixa_alta", False)), tamanho=int(fixa.get("tamanho", 66)))
        desde = fixa.get("desde", "fim_hook")
        t_fixa = fim_gancho if desde == "fim_hook" else float(desde)
        y_fixa = int(ALTURA * float(fixa.get("y", 0.07)))
        fim_fixa = t_fech if t_fech is not None else dur + 1
        entradas += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
        filtros.append(f"{atual}[{idx}:v]overlay=(W-w)/2:{y_fixa}:"
                       f"enable='between(t,{t_fixa:.3f},{fim_fixa:.3f})'[vx]")
        atual, idx = "[vx]", idx + 1

    # rótulos por corte depois do gancho (ex.: '12 reps', '8 x lado'), em ciclo
    rotulos = criativo.get("rotulos") or []
    if rotulos:
        janelas: dict[str, list[tuple[float, float]]] = {}
        k = 0
        limite = t_fech if t_fech is not None else dur
        for i, ini in enumerate(cortes):
            fim = cortes[i + 1] if i + 1 < len(cortes) else dur
            if ini < fim_gancho - 0.05 or ini >= limite:
                continue
            janelas.setdefault(rotulos[k % len(rotulos)], []).append((ini + 0.15, min(fim, limite)))
            k += 1
        for n, (texto, jan) in enumerate(janelas.items()):
            png = pasta / f"rotulo_{n}.png"
            _w, h = render_rotulo(texto, png)
            y_rot = y_leg + 40 - h
            cond = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in jan)
            entradas += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
            filtros.append(f"{atual}[{idx}:v]overlay=(W-w)/2:{y_rot}:enable='{cond}'[vr{n}]")
            atual, idx = f"[vr{n}]", idx + 1
    # textos com tempo (marcadores de lista, destaques do tour, rótulos fixos de cada metade)
    for n, tx in enumerate(textos):
        if tx["fim"] - tx["ini"] < 0.2:
            continue
        png = pasta / f"texto_{n}.png"
        render_faixa(tx["texto"], png, cor=cor_rgba(tx.get("cor"), (17, 17, 17, 255)),
                     cor_texto=cor_rgba(tx.get("cor_texto"), (255, 255, 255, 255)),
                     caixa_alta=bool(tx.get("caixa_alta", True)), tamanho=int(tx.get("tamanho", 62)))
        y_tx = int(ALTURA * float(tx.get("y", 0.30)))
        entradas += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
        filtros.append(f"{atual}[{idx}:v]overlay=(W-w)/2:{y_tx}:"
                       f"enable='between(t,{tx['ini']:.3f},{tx['fim']:.3f})'[vt{n}]")
        atual, idx = f"[vt{n}]", idx + 1
    filtros.append(f"{atual}[leg]overlay=0:{y_leg}:eof_action=pass,format=yuv420p[v]")

    # áudio: narração + whoosh nos cortes + pop no início + música opcional
    mix = ["[1:a]aresample=44100,volume=1.0[narr]"]
    rotulos = ["[narr]"]
    efeitos = oferta / "06_efeitos"
    if criativo.get("sfx", True) and (efeitos / "whoosh.mp3").exists():
        cortes_sfx = [c for c in cortes[1:] if c < dur - 0.3]
        if cortes_sfx:
            entradas += ["-i", efeitos / "whoosh.mp3"]
            mix.append(f"[{idx}:a]volume=0.32,asplit={len(cortes_sfx)}" + "".join(f"[w{i}]" for i in range(len(cortes_sfx))))
            for i, c in enumerate(cortes_sfx):
                ms = max(int((c - 0.22) * 1000), 0)
                mix.append(f"[w{i}]adelay={ms}|{ms}[wd{i}]")
                rotulos.append(f"[wd{i}]")
            idx += 1
        if (efeitos / "pop.mp3").exists():
            entradas += ["-i", efeitos / "pop.mp3"]
            mix.append(f"[{idx}:a]volume=0.5[pop]")
            rotulos.append("[pop]")
            idx += 1
    musicas = sorted(efeitos.glob("musica*.mp3")) if efeitos.is_dir() else []
    if musicas and criativo.get("musica", True):
        m = musicas[_semente(cid) % len(musicas)]
        entradas += ["-stream_loop", "-1", "-i", m]
        mix.append(f"[{idx}:a]volume={float(criativo.get('volume_musica', 0.10))},atrim=0:{dur:.3f}[mus]")
        rotulos.append("[mus]")
        idx += 1
    mix.append("".join(rotulos) + f"amix=inputs={len(rotulos)}:normalize=0:duration=first,"
               f"apad,atrim=0:{dur:.3f},alimiter=limit=0.95[a]")

    ffmpeg(*entradas, "-filter_complex", ";".join(filtros + mix), "-map", "[v]", "-map", "[a]",
           "-t", f"{dur:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", saida)


def _lufs(arquivo: Path) -> float | None:
    """Loudness integrada (EBU R128) do áudio do arquivo; None se não der para medir."""
    r = subprocess.run([binario("ffmpeg"), "-hide_banner", "-nostats", "-i", str(arquivo), "-vn",
                        "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    achados = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    try:
        valor = float(achados[-1])
    except (IndexError, ValueError):
        return None
    return valor if valor > -70 else None


def _normalizar_base(src: Path, inicio: float, destino: Path) -> None:
    vf = f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,crop={LARGURA}:{ALTURA},fps={FPS},setsar=1,format=yuv420p"
    if tem_audio(src):
        ffmpeg("-ss", f"{inicio:.3f}", "-i", src, "-vf", vf, *X264, "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", destino)
    else:
        ffmpeg("-ss", f"{inicio:.3f}", "-i", src, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
               "-vf", vf, "-shortest", *X264, "-c:a", "aac", "-b:a", "160k", destino)


def montar_criativo(oferta: Path, criativo: dict, estilo: str, ajustes: dict, narrar: bool) -> Path:
    cid = criativo["id"]
    pasta = oferta / "_work" / cid
    if pasta.exists():
        for sub in ("cima", "baixo", "cheia", "legendas"):
            shutil.rmtree(pasta / sub, ignore_errors=True)
    pasta.mkdir(parents=True, exist_ok=True)
    meta_path = oferta / "05_audios" / f"{cid}.palavras.json"
    if narrar or not meta_path.exists():
        meta = narrar_criativo(oferta, criativo, ajustes, refazer=False)
    else:
        meta = ler_json(meta_path)
    narr = oferta / "05_audios" / f"{cid}.mp3"
    saida = oferta / "01_prontos" / f"{cid}.mp4"

    base = criativo.get("base")
    if not base:
        compor(oferta, criativo, estilo, narr, meta, saida, pasta)
    else:
        # Variação de validado: hook novo narrado + body original do criativo que já vende.
        video = resolver(oferta, base["video"])
        if not video.exists():
            raise SystemExit(f"{cid}: vídeo base não encontrado: {video}")
        parte_a = pasta / "parte_hook.mp4"
        compor(oferta, criativo, estilo, narr, meta, parte_a, pasta)
        parte_b = pasta / "parte_body.mp4"
        _normalizar_base(video, float(base.get("a_partir_de", 0)), parte_b)
        # iguala o volume do hook novo ao do body original (sem isso há um salto de volume na emenda)
        la, lb = _lufs(parte_a), _lufs(parte_b)
        ganho = max(min(lb - la, 15.0), -15.0) if la is not None and lb is not None else 0.0
        if abs(ganho) > 0.5:
            log(f"{cid}: hook {la:.1f} LUFS → {lb:.1f} LUFS do validado ({ganho:+.1f} dB)")
        ffmpeg("-i", parte_a, "-i", parte_b, "-filter_complex",
               f"[0:a]volume={ganho:.2f}dB,alimiter=limit=0.95[a0];"
               "[0:v][a0][1:v][1:a]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", saida)
    log(f"{cid}: pronto → {saida} ({duracao(saida):.1f}s)")
    return saida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lote")
    ap.add_argument("--ids")
    ap.add_argument("--sem-narrar", action="store_true", help="não gerar narração; exige 05_audios/<id>.palavras.json")
    ap.add_argument("--manter-work", action="store_true")
    a = ap.parse_args()
    caminho = Path(a.lote)
    lote = ler_json(caminho)
    oferta = pasta_oferta(caminho)
    estilo_lote = lote.get("legenda", "variar")
    ajustes = lote.get("narracao", {"motor": "edge"})
    filtro = set(a.ids.split(",")) if a.ids else None
    feitos, falhas = [], []
    for i, criativo in enumerate(lote["criativos"]):
        if filtro and criativo["id"] not in filtro:
            continue
        estilo = criativo.get("legenda") or estilo_lote
        if estilo == "variar":
            estilo = "caixa_roxa" if i % 2 == 0 else "palavra_amarela"
        try:
            saida = montar_criativo(oferta, criativo, estilo, ajustes, narrar=not a.sem_narrar)
            feitos.append((criativo, estilo, saida))
            if not a.manter_work:
                shutil.rmtree(oferta / "_work" / criativo["id"], ignore_errors=True)
        except SystemExit as erro:
            log(f"{criativo['id']}: FALHOU — {erro}")
            falhas.append(criativo["id"])

    resumo = oferta / "01_prontos" / f"{caminho.stem}_resumo.csv"
    novo = not resumo.exists()
    with open(resumo, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["id", "modo", "angulo", "layout", "legenda", "hook", "duracao_s", "arquivo"])
        for criativo, estilo, saida in feitos:
            w.writerow([criativo["id"], lote.get("modo", ""), criativo.get("angulo", ""), criativo.get("layout", "dividida"),
                        estilo, criativo.get("hook", ""), f"{duracao(saida):.1f}", saida.name])
    print(f"Prontos: {len(feitos)} | falhas: {len(falhas)} {falhas if falhas else ''}")
    print(f"Pasta: {oferta / '01_prontos'}")
    if falhas:
        raise SystemExit(1)


if __name__ == "__main__":
    configurar_saida()
    main()
