#!/usr/bin/env python3
"""Divide vídeos do usuário em cenas (planos) limpas, prontas para o b-roll da montagem.

Uso:
  python cenas.py "<pasta_oferta>" "<video.mp4>" [--de S] [--ate S] [--prefixo nome]
                  [--limiar 0.30] [--min 1.2] [--pasta 02_brutos] [--listar]

- Detecta trocas de plano (ffmpeg scene detection) e grava cada plano como um clipe sem áudio:
  <pasta>/<prefixo>_01.mp4, _02.mp4…
- --de / --ate: usa só esse trecho do vídeo (ex.: corta o anúncio de outra marca no fim).
- --min: planos mais curtos que isso são descartados (viram piscada na montagem).
- --listar: só mostra as cenas encontradas, sem gravar.
Vídeos compilados (vários planos de banco) viram vários clipes; um vídeo de demonstração contínuo vira um só.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from comum import binario, configurar_saida, duracao, ffmpeg, log


def detectar_cortes(video: Path, de: float, ate: float, limiar: float) -> list[float]:
    r = subprocess.run([binario("ffmpeg"), "-hide_banner", "-nostats", "-ss", f"{de:.3f}", "-to", f"{ate:.3f}",
                        "-i", str(video), "-an", "-vf", f"select='gt(scene,{limiar})',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [de + float(t) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def main() -> None:
    configurar_saida()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("oferta")
    ap.add_argument("video")
    ap.add_argument("--de", type=float, default=0.0)
    ap.add_argument("--ate", type=float, default=0.0, help="0 = até o fim")
    ap.add_argument("--prefixo")
    ap.add_argument("--limiar", type=float, default=0.30)
    ap.add_argument("--min", type=float, default=1.2)
    ap.add_argument("--pasta", default="02_brutos")
    ap.add_argument("--listar", action="store_true")
    a = ap.parse_args()

    video, oferta = Path(a.video), Path(a.oferta)
    total = duracao(video)
    ate = a.ate if 0 < a.ate <= total else total
    bordas = [a.de] + [t for t in detectar_cortes(video, a.de, ate, a.limiar) if a.de + 0.3 < t < ate - 0.3] + [ate]
    cenas = [(i, f) for i, f in zip(bordas, bordas[1:]) if f - i >= a.min]
    prefixo = a.prefixo or re.sub(r"[^\w]+", "_", video.stem.lower())[:30]
    destino = oferta / a.pasta
    destino.mkdir(parents=True, exist_ok=True)
    for n, (i, f) in enumerate(cenas, 1):
        nome = destino / f"{prefixo}_{n:02d}.mp4"
        print(f"{nome.name}: {i:6.2f}–{f:6.2f}s ({f - i:.1f}s)")
        if a.listar:
            continue
        # recorta 0,1 s de cada ponta para não pegar quadro de transição
        ini, fim = i + 0.1, f - 0.1
        ffmpeg("-ss", f"{ini:.3f}", "-to", f"{fim:.3f}", "-i", video, "-an", "-vf", "setsar=1,format=yuv420p",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", nome)
    log(f"{len(cenas)} cenas de {video.name} ({len(bordas) - 1 - len(cenas)} curtas demais descartadas)")


if __name__ == "__main__":
    main()
