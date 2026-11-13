#!/usr/bin/env python3
"""Cria (ou completa) a estrutura de pastas de uma oferta.

Uso: python criar_oferta.py "Velas de Natal" ["~/Documents/Ofertas"]
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
from pathlib import Path

from comum import PASTAS, RAIZ_PADRAO, SFX_DIR, configurar_saida, gravar_json, log
from gerar_sfx import gerar

LEIA_ME = {
    "02_brutos": "Vídeos de referência e b-roll da oferta (baixados ou gravados). Use baixar.py para links.",
    "03_apresentadora": "Gravações de UGC / apresentadora falando para a câmera.",
    "04_imagens": "Fotos do produto, prints da página, imagens de apoio.",
    "05_audios": "Narrações. Se já tiver os áudios, nomeie como <id_do_criativo>.mp3.",
    "06_efeitos": "Efeitos sonoros. Coloque aqui musica*.mp3 para trilha de fundo.",
    "07_roteiros": "Lotes de roteiros (.json) gerados pelo Claude.",
    "08_validados": "Criativos que já vendem — base para 'Variações de validados' e 'Modelagem'.",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nome")
    parser.add_argument("raiz", nargs="?", default=str(RAIZ_PADRAO))
    args = parser.parse_args()

    oferta = Path(args.raiz).expanduser() / args.nome.strip()
    for pasta in PASTAS:
        (oferta / pasta).mkdir(parents=True, exist_ok=True)
    for pasta, texto in LEIA_ME.items():
        leia = oferta / pasta / "LEIA-ME.txt"
        if not leia.exists():
            leia.write_text(texto + "\n", encoding="utf-8")

    gerar()
    copiados = 0
    for sfx in sorted(SFX_DIR.glob("*.mp3")):
        destino = oferta / "06_efeitos" / sfx.name
        if not destino.exists():
            shutil.copy2(sfx, destino)
            copiados += 1

    meta = oferta / "oferta.json"
    if not meta.exists():
        gravar_json(meta, {"nome": args.nome.strip(), "criado": dt.date.today().isoformat(),
                           "produto": "", "publico": "", "promessa": "", "pagina": "", "observacoes": ""})

    print(f"Oferta: {oferta}")
    print(f"Pastas: {len(PASTAS)} | efeitos copiados: {copiados}")
    log("estrutura pronta")


if __name__ == "__main__":
    configurar_saida()
    main()
