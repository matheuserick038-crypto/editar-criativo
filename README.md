# editar-criativo

Skill do [Claude Code](https://claude.com/claude-code) que produz **criativos de vídeo em lote** para
anúncios 9:16 (Meta Ads / TikTok): roteiro, narração, b-roll cortado no ritmo da fala, faixa de gancho,
legenda palavra a palavra, efeitos sonoros e exportação pronta para subir.

Você pede "edite meus criativos da oferta X" e o Claude:

1. cria a pasta da oferta (`01_prontos`, `02_brutos`, `04_imagens`, `05_audios`, `07_roteiros`…);
2. pergunta o modo, a quantidade, o estilo de legenda e o tipo de narração;
3. busca imagens e vídeos grátis (Pixabay/Pexels), **primeiro numa biblioteca local** para não gastar requisição;
4. escreve os roteiros (hook + body) num lote JSON;
5. narra, monta e exporta tudo em `01_prontos/`, com um `.csv` de resumo para nomear os anúncios.

## Modos

| Modo | O que faz |
|---|---|
| **Criativos novos** | N roteiros com ângulos diferentes (dor, curiosidade, objeção, preço, teste…). |
| **Modelagem** | Vídeos do zero com a estrutura de um criativo que já vende (o seu ou do mercado): mesmos blocos de fala, faixa fixa com preço, contador de repetições, voz e legenda — com roteiro e imagens novos. |
| **Variações de validado** | Reaproveita o próprio vídeo validado e troca só o hook (hook novo narrado + corpo original, com volume igualado). |

## O que o kit monta

- **Layouts**: tela dividida (duas mídias com linha vermelha no meio) ou tela cheia.
- **Faixa de gancho** vermelha no início; **faixa fixa** (ex.: nome + preço) depois do gancho; **CTA** verde no fim.
- **Legenda palavra a palavra**: caixa roxa ou palavra amarela.
- **Rótulos** sobre cada corte ("12 reps", "8 x lado").
- **Fechamento** com a capa do produto ou print da página sobre fundo desfocado.
- **Encaixe com desfoque** para vídeo horizontal em tela vertical (não perde o movimento).
- **Efeitos sonoros** gerados pelo próprio kit (whoosh nos cortes, pop no início) e trilha opcional (`06_efeitos/musica*.mp3`).
- **Narração**: vozes neurais grátis (edge-tts), ElevenLabs ou áudio próprio (transcrito com Whisper local).

## Instalação

1. Copie esta pasta para `~/.claude/skills/editar-criativo` (no Windows: `%USERPROFILE%\.claude\skills\editar-criativo`).
2. Instale as dependências:
   - Python 3.10+
   - [ffmpeg](https://ffmpeg.org/) no PATH
   - `pip install pillow edge-tts`
   - Opcional: `yt-dlp` (baixar referências de redes sociais)
   - Opcional: Whisper local para transcrever áudio próprio/vídeos de referência — o kit usa o ambiente
     `~/.cache/watch/whisperx-venv` criado pela skill [claude-video (watch)](https://github.com/bradautomates/claude-video)
     com `--backend whisperx`.
3. Chaves (opcionais, grátis) em `~/.config/editar-criativo/.env`:

   ```
   PIXABAY_API_KEY=
   PEXELS_API_KEY=
   ELEVENLABS_API_KEY=
   ELEVENLABS_VOICE_ID=
   ```

## Uso

No Claude Code, peça em linguagem natural — por exemplo:

- "edite 10 criativos para a oferta Velas de Natal"
- "esse é meu criativo validado, cria 5 variações do zero"
- "/editar-criativo"

Ou rode os scripts direto:

```bash
python kit/criar_oferta.py "Velas de Natal"
python kit/buscar_midias.py "~/Documents/Ofertas/Velas de Natal" "candle making" --qtd 6
python kit/montar.py "~/Documents/Ofertas/Velas de Natal/07_roteiros/lote_01.json"
```

O formato do lote JSON e todos os campos estão documentados no [SKILL.md](SKILL.md).

## Observações

- Imagens e vídeos de banco (Pixabay/Pexels) são de uso comercial liberado; os créditos ficam em `02_brutos/creditos.csv`.
- Não use banco de imagens para simular depoimento, nem prometa cura/renda garantida — respeite as políticas de anúncio.
- A voz grátis (edge-tts) depende de internet e falha de vez em quando; o kit tenta de novo sozinho.
