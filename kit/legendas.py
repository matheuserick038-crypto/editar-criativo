"""Renderiza legendas palavra-a-palavra e a faixa de gancho como PNG transparentes (Pillow).

Estilos de legenda:
  caixa_roxa       palavra falada dentro de uma caixa roxa, demais em branco com contorno
  palavra_amarela  palavra falada em amarelo, sem fundo
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from comum import LARGURA, fonte

ROXO = (124, 58, 237, 255)
AMARELO = (255, 224, 27, 255)
BRANCO = (255, 255, 255, 255)
PRETO = (0, 0, 0, 255)
VERMELHO = (225, 29, 42, 255)

ALTURA_CANVAS_LEGENDA = 360
TAM_LEGENDA = 84
TAM_GANCHO = 62
LARGURA_UTIL = 960


def _fonte(tipo: str, tamanho: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(fonte(tipo), tamanho)


def agrupar(palavras: list[dict], max_palavras: int = 3, max_chars: int = 18) -> list[list[dict]]:
    grupos, atual = [], []
    for p in palavras:
        texto = p["t"]
        tamanho = sum(len(x["t"]) + 1 for x in atual) + len(texto)
        if atual and (len(atual) >= max_palavras or tamanho > max_chars):
            grupos.append(atual)
            atual = []
        atual.append(p)
        if re.search(r"[.!?;:]$", texto):
            grupos.append(atual)
            atual = []
    if atual:
        grupos.append(atual)
    return grupos


def _quebrar_linhas(textos: list[str], f: ImageFont.FreeTypeFont, espaco: int, largura: int) -> list[list[int]]:
    linhas, atual, w = [], [], 0
    for i, t in enumerate(textos):
        lw = f.getlength(t)
        if atual and w + espaco + lw > largura:
            linhas.append(atual)
            atual, w = [], 0
        w += (espaco if atual else 0) + lw
        atual.append(i)
    if atual:
        linhas.append(atual)
    return linhas


def render_legenda(textos: list[str], ativo: int, estilo: str, destino: Path) -> None:
    textos = [re.sub(r"(?<!\.)[,;:.]$", "", t).upper() for t in textos]  # mantém ? ! e reticências
    f = _fonte("legenda", TAM_LEGENDA)
    espaco = int(TAM_LEGENDA * 0.28)
    contorno = 7
    img = Image.new("RGBA", (LARGURA, ALTURA_CANVAS_LEGENDA), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    linhas = _quebrar_linhas(textos, f, espaco, LARGURA_UTIL)
    asc, desc = f.getmetrics()
    altura_linha = asc + desc + 14
    y = (ALTURA_CANVAS_LEGENDA - altura_linha * len(linhas)) // 2
    for linha in linhas:
        larguras = [f.getlength(textos[i]) for i in linha]
        total = sum(larguras) + espaco * (len(linha) - 1)
        x = (LARGURA - total) / 2
        for i, lw in zip(linha, larguras):
            if i == ativo and estilo == "caixa_roxa":
                pad_x, pad_y = 16, 8
                d.rounded_rectangle([x - pad_x, y - pad_y + 6, x + lw + pad_x, y + asc + desc + pad_y - 4],
                                    radius=18, fill=ROXO)
                d.text((x, y), textos[i], font=f, fill=BRANCO)
            else:
                cor = AMARELO if (i == ativo and estilo == "palavra_amarela") else BRANCO
                d.text((x, y), textos[i], font=f, fill=cor, stroke_width=contorno, stroke_fill=PRETO)
            x += lw + espaco
        y += altura_linha
    img.save(destino)


def cor_rgba(valor, padrao=BRANCO) -> tuple[int, int, int, int]:
    """Aceita '#RRGGBB' ou [r, g, b] (do JSON do lote)."""
    if not valor:
        return padrao
    if isinstance(valor, str):
        v = valor.lstrip("#")
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), 255
    return tuple(valor[:3]) + (255,)


def render_faixa(texto: str, destino: Path, cor=VERMELHO, cor_texto=BRANCO, caixa_alta: bool = True,
                 tamanho: int = TAM_GANCHO) -> tuple[int, int]:
    """Faixa (gancho, CTA ou faixa fixa): caixa colorida com texto centralizado. '\\n' força quebra de linha.
    Devolve (largura, altura)."""
    f = _fonte("gancho", tamanho)
    texto = texto.upper() if caixa_alta else texto
    espaco = int(tamanho * 0.3)
    palavras, linhas = [], []
    for trecho in texto.split("\n"):
        base = len(palavras)
        pals = trecho.split()
        palavras += pals
        linhas += [[base + i for i in ln] for ln in _quebrar_linhas(pals, f, espaco, 880)]
    asc, desc = f.getmetrics()
    altura_linha = asc + desc + 4
    larg_linhas = [f.getlength(" ".join(palavras[i] for i in ln)) for ln in linhas]
    pad_x, pad_y = 30, 20
    w = int(max(larg_linhas) + 2 * pad_x)
    h = int(altura_linha * len(linhas) + 2 * pad_y)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=16, fill=cor)
    y = pad_y
    for ln, lw in zip(linhas, larg_linhas):
        d.text(((w - lw) / 2, y), " ".join(palavras[i] for i in ln), font=f, fill=cor_texto)
        y += altura_linha
    img.save(destino)
    return w, h


def render_rotulo(texto: str, destino: Path, tamanho: int = 60) -> tuple[int, int]:
    """Rótulo pequeno sobre o exercício (ex.: '12 reps', '8 x lado'): branco com contorno, sem caixa."""
    f = _fonte("legenda", tamanho)
    contorno = 5
    w = int(f.getlength(texto)) + 2 * contorno + 8
    asc, desc = f.getmetrics()
    h = asc + desc + 2 * contorno
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((contorno + 4, contorno), texto, font=f, fill=BRANCO,
                             stroke_width=contorno, stroke_fill=PRETO)
    img.save(destino)
    return w, h


def trilha_legendas(palavras: list[dict], estilo: str, duracao_total: float, pasta: Path) -> Path:
    """Gera PNGs + roteiro ffconcat (imagem e duração). Devolve o caminho do .txt."""
    pasta.mkdir(parents=True, exist_ok=True)
    vazio = pasta / "vazio.png"
    Image.new("RGBA", (LARGURA, ALTURA_CANVAS_LEGENDA), (0, 0, 0, 0)).save(vazio)
    eventos: list[tuple[Path, float]] = []  # (imagem, instante de início)
    grupos = agrupar(palavras)
    n = 0
    for gi, grupo in enumerate(grupos):
        fim_grupo = grupos[gi + 1][0]["ini"] if gi + 1 < len(grupos) else grupo[-1]["fim"] + 0.35
        textos = [p["t"] for p in grupo]
        for wi, p in enumerate(grupo):
            arq = pasta / f"leg_{n:04d}.png"
            render_legenda(textos, wi, estilo, arq)
            eventos.append((arq, p["ini"]))
            n += 1
        # se houver silêncio longo até o próximo grupo, esconde a legenda
        if gi + 1 < len(grupos) and fim_grupo - grupo[-1]["fim"] > 0.7:
            eventos.append((vazio, grupo[-1]["fim"] + 0.35))
    if not eventos or eventos[0][1] > 0:
        eventos.insert(0, (vazio, 0.0))
    eventos.append((vazio, min(duracao_total, max(e[1] for e in eventos) + 0.01)))
    linhas = ["ffconcat version 1.0"]
    for (img, ini), (_prox, prox_ini) in zip(eventos, eventos[1:] + [(vazio, duracao_total)]):
        dur = max(prox_ini - ini, 1 / 30)
        linhas.append(f"file '{img.as_posix()}'")
        linhas.append(f"duration {dur:.3f}")
    linhas.append(f"file '{vazio.as_posix()}'")
    roteiro = pasta / "legendas.ffconcat"
    roteiro.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return roteiro
