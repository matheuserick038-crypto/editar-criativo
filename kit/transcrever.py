#!/usr/bin/env python3
"""Transcreve um áudio/vídeo com tempo por palavra (faster-whisper local, modelo small).

Uso: python transcrever.py <midia> [saida.json] [--idioma pt]
Sem saída explícita, grava <midia>.palavras.json ao lado do arquivo.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from comum import WHISPER_PY, KIT_DIR, binario, configurar_saida, ler_json, log, rodar


def transcrever(midia: Path, saida: Path | None = None, idioma: str = "pt") -> dict:
    if not WHISPER_PY.is_file():
        raise SystemExit("WhisperX local não está instalado (rode o setup da skill watch com --backend whisperx).")
    saida = saida or midia.with_suffix(midia.suffix + ".palavras.json")
    log(f"transcrevendo {midia.name} (CPU, pode levar alguns minutos)…")
    rodar([WHISPER_PY, KIT_DIR / "_palavras_whisper.py", midia, saida, idioma, binario("ffmpeg")])
    return ler_json(saida)


if __name__ == "__main__":
    configurar_saida()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("midia")
    ap.add_argument("saida", nargs="?")
    ap.add_argument("--idioma", default="pt")
    a = ap.parse_args()
    dados = transcrever(Path(a.midia), Path(a.saida) if a.saida else None, a.idioma)
    texto = " ".join(p["t"] for p in dados["palavras"])
    print(texto)
