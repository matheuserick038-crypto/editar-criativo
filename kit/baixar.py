#!/usr/bin/env python3
"""Baixa vídeos de referência (TikTok, Instagram, YouTube, Biblioteca de Anúncios…) para 02_brutos.

Uso: python baixar.py <pasta_da_oferta> <url> [<url> ...] [--pasta 02_brutos|08_validados]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from comum import binario, configurar_saida, log, rodar


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("oferta")
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--pasta", default="02_brutos")
    a = ap.parse_args()
    destino = Path(a.oferta) / a.pasta
    destino.mkdir(parents=True, exist_ok=True)
    ok, falhas = 0, []
    for url in a.urls:
        try:
            rodar([binario("yt-dlp"), "--no-playlist", "--restrict-filenames",
                   "-f", "bv*[height<=1920]+ba/b", "--merge-output-format", "mp4",
                   "-o", str(destino / "%(extractor)s_%(id)s.%(ext)s"), url])
            ok += 1
            log(f"baixado: {url}")
        except SystemExit as erro:
            falhas.append(url)
            log(f"falhou: {url} — {str(erro)[-300:]}")
    print(f"Baixados: {ok} | falhas: {len(falhas)}")


if __name__ == "__main__":
    configurar_saida()
    main()
