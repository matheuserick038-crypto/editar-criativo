#!/usr/bin/env python3
"""Sintetiza os 9 efeitos sonoros padrão do kit com ffmpeg (sem downloads)."""
from __future__ import annotations

from comum import SFX_DIR, configurar_saida, ffmpeg, log

# nome -> filtro lavfi (mono 44.1 kHz)
EFEITOS = {
    "whoosh": "anoisesrc=d=0.55:c=pink:a=0.7,highpass=f=350,lowpass=f=5000,"
              "afade=t=in:d=0.28:curve=qsin,afade=t=out:st=0.28:d=0.27:curve=qsin",
    "swoosh": "anoisesrc=d=0.3:c=white:a=0.45,highpass=f=1200,lowpass=f=8000,"
              "afade=t=in:d=0.12,afade=t=out:st=0.12:d=0.18",
    "pop": "aevalsrc='0.9*sin(2*PI*(900-2500*t)*t)*exp(-38*t)':d=0.14",
    "click": "anoisesrc=d=0.03:c=white:a=0.8,highpass=f=2500,afade=t=out:d=0.03",
    "ding": "aevalsrc='0.5*sin(2*PI*1318*t)*exp(-4*t)+0.25*sin(2*PI*2636*t)*exp(-6*t)':d=0.9",
    "impacto": "aevalsrc='0.9*sin(2*PI*(70-40*t)*t)*exp(-5*t)':d=0.8,lowpass=f=300",
    "riser": "aevalsrc='0.35*sin(2*PI*(180*t+380*t*t))':d=1.2,afade=t=in:d=1.0:curve=exp,afade=t=out:st=1.1:d=0.1",
    "glitch": "anoisesrc=d=0.3:c=white:a=0.5,tremolo=f=28:d=1,bandpass=f=1800:w=900",
    "notificacao": "aevalsrc='0.5*sin(2*PI*880*t)*exp(-9*t)*lt(t,0.15)+0.5*sin(2*PI*1175*(t-0.15))*exp(-7*(t-0.15))*gte(t,0.15)':d=0.6",
}


def gerar(forcar: bool = False) -> int:
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    criados = 0
    for nome, filtro in EFEITOS.items():
        destino = SFX_DIR / f"{nome}.mp3"
        if destino.exists() and not forcar:
            continue
        ffmpeg("-f", "lavfi", "-i", filtro, "-ac", "1", "-ar", "44100", "-b:a", "128k", str(destino))
        criados += 1
    return criados


if __name__ == "__main__":
    configurar_saida()
    import sys
    n = gerar(forcar="--forcar" in sys.argv)
    log(f"efeitos sintetizados: {n} (pasta {SFX_DIR})")
