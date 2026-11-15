---
name: editar-criativo
description: Fábrica de criativos de vídeo em lote para ofertas (anúncios 9:16 para Meta/TikTok). Cria a pasta da oferta, escreve roteiros (hook + body), gera narração (voz neural grátis, ElevenLabs ou áudio próprio), corta b-roll no ritmo da fala, aplica faixa de gancho, legenda palavra-a-palavra (caixa roxa ou palavra amarela), efeitos sonoros e trilha, e exporta tudo pronto em 01_prontos. Três modos — criativos novos, modelagem de um criativo que já escala, variações de hook sobre um criativo validado. Use sempre que o usuário disser "editar criativo", "edite meu criativo", "/editar-criativo", pedir para fazer/gerar/montar/editar criativos, variações de criativo, novos hooks, modelar um anúncio, ou volume de criativos para testar oferta — mesmo sem dizer "skill".
allowed-tools: Bash, PowerShell, Read, Write, Edit, Glob, AskUserQuestion, WebSearch, Skill
---

# Editar criativo

Kit em `kit/` (ao lado deste arquivo). Todos os scripts são Python 3.10+ e usam ffmpeg/ffprobe.
No Windows rode com `python` (não `python3`). Se `ffmpeg` não estiver no PATH da sessão, os scripts
o encontram pelo PATH do usuário automaticamente.

```
KIT = <pasta deste SKILL.md>/kit
```

## 1. Oferta e pastas

Descubra o nome da oferta (pergunte se não veio no pedido). Raiz padrão: `~/Documents/Ofertas` (no Windows, `%USERPROFILE%\Documents\Ofertas`).

```powershell
python "$KIT/criar_oferta.py" "Velas de Natal"
```

Cria (ou completa, sem apagar nada) a estrutura:

| Pasta | Conteúdo |
|---|---|
| `_work` | temporários (limpos ao final) |
| `01_prontos` | criativos finais `.mp4` + `lote_XX_resumo.csv` |
| `02_brutos` | b-roll e vídeos de referência |
| `03_apresentadora` | gravações de UGC / apresentadora |
| `04_imagens` | fotos do produto, prints da página |
| `05_audios` | narrações (`<id>.mp3` + `<id>.palavras.json`) |
| `06_efeitos` | 9 efeitos sonoros do kit + `musica*.mp3` opcionais (trilha) |
| `07_roteiros` | lotes de roteiro `.json` |
| `08_validados` | criativos que já vendem (base para modelagem/variação) |

Leia `oferta.json`. Se `produto`/`publico`/`promessa` estiverem vazios, pergunte ao usuário (ou leia a
página de vendas se ele passar o link) e preencha — os roteiros dependem disso.

## 2. As quatro perguntas (uma única chamada AskUserQuestion)

1. **Modo — "O que vamos fazer?"**
   - Criativos novos — testar ângulos e roteiros novos
   - Modelagem de criativos — vídeos do zero com a estrutura de um criativo que já vende/escala
     (do próprio usuário ou do mercado)
   - Variações de validados — reaproveitar o próprio vídeo validado e trocar só o hook

**Atenção — "melhora esse validado e cria variações":** quando o usuário manda um criativo dele que vende e
pede variações/versões melhores, o padrão é **Modelagem** (vídeos totalmente novos, com roteiro e imagens
novas, usando o validado só como referência de estrutura). Só use "Variações de validados" (que reaproveita
as imagens e o áudio do vídeo enviado) se o usuário pedir explicitamente para manter o vídeo original.
2. **Quantidade — "Quantas variações?"** 5 / 10 / 20 / 50
3. **Legenda — "Qual estilo de legenda?"**
   - Variar entre os dois (Recomendado) — alterna caixa roxa e palavra amarela entre as variações
   - Caixa roxa — palavra falada dentro de uma caixa roxa
   - Palavra amarela — palavra falada em amarelo, sem fundo
4. **Narração — "Como vamos fazer a narração dos novos hooks e bodies?"**
   - Gerar com voz grátis (Recomendado) — vozes neurais em português, sem custo
   - Gerar com ElevenLabs — usa a conta do usuário e consome créditos
   - Já tenho as narrações — coloco os áudios em 05_audios

Se o usuário já respondeu algo no pedido, não pergunte de novo.

**ElevenLabs:** a chave fica em `~/.config/editar-criativo/.env` (`ELEVENLABS_API_KEY=` e, opcional,
`ELEVENLABS_VOICE_ID=`). Se faltar, ofereça abrir o arquivo no Bloco de Notas para o usuário colar.
Nunca imprima a chave nem a coloque em comando de shell.

## 3. Material visual

Liste `02_brutos`, `03_apresentadora` e `04_imagens`. Fontes de material, nesta ordem de preferência:

1. **Material do próprio usuário** (fotos/vídeos do produto, gravação da página): sempre o melhor.
   - **Vídeos que o usuário baixou** (Pinterest, TikTok, Reels — às vezes numa pasta à parte, separados por
     tema): faça uma folha de miniaturas (5 quadros por vídeo) para ver o conteúdo, depois corte em cenas limpas:
     ```powershell
     python "$KIT/cenas.py" "<pasta_oferta>" "<video.mp4>" --prefixo usr_costas_a --ate 8.0
     python "$KIT/cenas.py" "<pasta_oferta>" "<video.mp4>" --listar   # só mostra as cenas
     ```
     Cada troca de plano vira um clipe sem áudio em `02_brutos/<prefixo>_NN.mp4`. Use `--ate`/`--de` para
     deixar de fora o que não pode entrar: **anúncio/logo/site de outra marca no fim** (comum em compilações),
     vinheta, número animado. Use prefixos por tema (`usr_pc_`, `usr_costas_`, `usr_demo_`) — facilita montar
     `midias_gancho` (clipes de problema/dor) e `midias` (demonstração).
   - Evite no corpo clipes com texto gravado no meio da tela (conflita com `rotulos`); texto no topo some
     sob a `faixa_fixa`. Vídeo de terceiros: avise o usuário do risco de direitos autorais em anúncio pago.
2. **Bancos gratuitos (Pexels + Pixabay)** — b-roll de apoio, uso comercial liberado:
   ```powershell
   python "$KIT/buscar_midias.py" "<pasta_oferta>" "candle making" --qtd 6
   python "$KIT/buscar_midias.py" "<pasta_oferta>" "christmas candle" --tipo foto --qtd 4
   ```
   - Faça 3–5 buscas com termos **em inglês** que cubram o que a narração mostra (processo, ingredientes,
     resultado, cena de uso, emoção). `--listar` mostra antes de baixar.
   - **Biblioteca local primeiro:** todo download fica em `~/Documents/Ofertas/_biblioteca`
     (`videos/`, `fotos/`, `indice.json` com as tags do banco + termos já buscados). Cada busca procura lá antes
     e só chama a API para o que faltar — economiza requisições. Os arquivos entram na oferta por hardlink (sem
     ocupar espaço duplicado). `--sem-api` usa só a biblioteca; `--forcar-api` ignora a biblioteca.
     Por isso use termos em inglês consistentes entre ofertas ("stretching", "back pain", "yoga mat"…).
   - Padrão: prefere vertical e completa com horizontal (o kit recorta), vídeos de até 40 s, `--qtd` itens
     novos de cada tipo. Vídeos vão para `02_brutos/`, fotos para `04_imagens/`, créditos em
     `02_brutos/creditos.csv` (coluna `origem`: biblioteca ou banco).
   - Depois de baixar, escolha as mídias certas para cada criativo em `midias`/`midias_baixo` em vez de
     deixar o sorteio — b-roll que combina com a fala converte mais.
   - Não use banco de imagens para simular depoimento: pessoa reconhecível não pode parecer endossar a oferta.
   - Chaves grátis em `~/.config/editar-criativo/.env` (`PEXELS_API_KEY`, `PIXABAY_API_KEY`). Se faltar,
     o script avisa; ofereça abrir o arquivo no Bloco de Notas para o usuário colar. Funciona com uma só.
     (Em nov/2026 o Pexels pausou a emissão de chaves novas; o usuário usa só o Pixabay até reabrir.)
3. **Referências de redes sociais** (para modelagem/variação), com links que o usuário aprovar:
   `python "$KIT/baixar.py" "<pasta_oferta>" <url1> <url2> ... --pasta 08_validados`.
   Use apenas material que o usuário tem direito de usar.

Gravação de tela do web app / página: o usuário grava (Win+Alt+R) e salva em `02_brutos`.

## 4. Roteiros por modo

Escreva em português do Brasil (ou de Portugal se a oferta for PT), tom UGC falado, frases curtas.
- **hook**: 1 frase, 6–14 palavras, ≤ 3 s falado. Quebra padrão, curiosidade, dor ou resultado.
- **gancho_tela**: texto da faixa vermelha, ≤ 7 palavras, complementa (não repete) o hook.
- **body**: 15–35 s falados (~40–90 palavras): problema → mecanismo/demonstração → prova → CTA.
- **cta_tela** (opcional): texto curto da faixa verde nos últimos 3 s ("LINK NA DESCRIÇÃO").
- Varie ângulos no lote: dor, curiosidade, antes/depois, prova social, objeção, demonstração, preço/ancoragem,
  urgência sazonal, "erro comum", lista. Não repita a mesma abertura.
- Respeite políticas de anúncio: nada de promessa de cura, renda garantida, ou "você é [atributo pessoal]".

**Criativos novos:** N roteiros com ângulos diferentes.

**Avatar do usuário** (documento de persona/pesquisa — ex.: "SEARCH 1 - <oferta>.txt" no cofre): leia inteiro e
escreva a partir dele, não de suposições. Use: subnicho prioritário; cenas de "Everyday Life Relatability"
como gancho (reconhecível em 2 s); as palavras de "Verbal Triggers" (e evite as que espantam); "Common Enemy";
"False Solutions" e "Comparisons" (listas e preço); objeções e "Confusions" (formato pergunta); "Metaphor
Mapping"; tom de "Communication Style". **O preço e a oferta vêm do documento** — se divergirem do validado ou
de lotes antigos, siga o documento e avise o usuário. Inclua o rodapé "Não substitui acompanhamento
profissional." quando o documento pedir. Duração pedida (ex.: ~35 s ≈ 90 palavras com a voz Thalita a +0%).

**Formatos** (quando o usuário pedir "outros formatos" ou variar além do ângulo) — receitas com o kit:
| Formato | Como montar |
|---|---|
| Tela dividida "parado × em movimento" | `layout: dividida`, `gancho_tela: false`, `midias` = problema (cima), `midias_baixo` = solução; `textos` fixos `desde: 0` com `y` ≈ 0.425 (vermelho, cima) e 0.515 (verde, baixo) |
| Tour pela área de membros / produto | gravação da área (celular filmando ou tela) cortada por seção; `midias` na ordem das falas, `ritmo` alto, `textos` destacando cada seção (`y` ≈ 0.76) |
| Pergunta frequente (quebra de objeção) | `gancho_estilo: "pergunta"`, hook = a pergunta; body responde mostrando o produto |
| Lista numerada ("3 testes", "3 erros") | `textos` "Teste 1/2/3" em `palavra:primeiro/segundo/terceiro`, `ritmo` 12, uma mídia por item |
| Comparação de preço ("o que R$ 10 compra") | `textos` por item em `palavra:lanche`… com a mídia de cada item, fecha no produto |
| Depoimento | **Só com depoimento real** do usuário (vídeo/print de cliente). Nunca invente depoimento, cliente, comentário ou resultado — é propaganda enganosa e reprova no Meta. Sem material real, ofereça "Pergunta frequente". |

Área de membros/app gravado em 4K/HEVC: corte por seção e reduza antes (`ffmpeg -ss A -to B -i x.MOV -an
-vf "scale=1080:-2,fps=30" ... 02_brutos/area_<secao>.mp4`) — a montagem fica muito mais rápida.

**Modelagem de criativos:** o criativo de referência fica em `08_validados` (ou baixe pelo link). Transcreva:
`python "$KIT/transcrever.py" "<arquivo>"` — e, se a parte visual importar, assista com a skill `watch`.
Mapeie a estrutura (tipo de hook, blocos e duração de cada um, CTA) e escreva N roteiros com **a mesma estrutura**
para esta oferta. Não copie o texto. Nenhum quadro nem áudio do vídeo de referência entra nos vídeos novos.

Checklist de modelagem (anote no lote em `estrutura_modelada`):
1. **Duração e blocos de fala** — ex.: gancho 0–3,5 s → apresenta o produto → benefícios → CTA com preço.
2. **Formato visual** — tela cheia ou dividida; o que aparece o tempo todo (demonstração, apresentadora, tela).
3. **Elementos fixos que vendem** — reproduza com o kit:
   - faixa com nome + preço fixa no topo → `faixa_fixa` (entra **depois** do gancho, para não ter cara de
     anúncio no 1º segundo);
   - contador sobre o exercício/passo ("12 reps", "8 x lado") → `rotulos`;
   - estilo de legenda e gênero da voz → `legenda` e `voz` iguais aos do validado.
4. **Preço e oferta** exatamente como no validado (é o que ele vende), salvo pedido em contrário.
5. **Se o validado tem CTR baixo e venda boa:** o corpo funciona e a abertura não para o dedo. Mantenha a
   estrutura do corpo e invista no gancho: tensão, teste ("tenta encostar a mão no chão…"), número/conta
   ("117 exercícios por menos de R$ 10"), quebra de crença. Faixa de gancho desde 0 s, imagens próprias do
   gancho em `midias_gancho` (moedas, esqueleto, academia), cortes a cada ~1,8 s, e `encaixe: "desfoque"`
   quando o b-roll for horizontal em tela cheia.

**Variações de validados** (só quando o usuário quer manter o vídeo original): transcreva o criativo que já vende, encontre onde o hook original termina
(fim da 1ª frase, geralmente 2–5 s) e escreva N hooks novos. Cada criativo leva só `hook` (sem `body`) e
`"base": {"video": "08_validados/arquivo.mp4", "a_partir_de": <segundos>}` — o kit monta hook novo narrado +
body original com o áudio original.
- Corte em `a_partir_de` logo antes da 1ª palavra depois do hook (pule o silêncio — ex.: hook acaba em 3,56 s,
  próxima palavra em 4,16 s → 4,05). Use `transcrever.py` para ter o tempo de cada palavra.
- Use voz do mesmo gênero da narração original (a emenda soa estranha com troca de voz) e a mesma legenda
  do validado, se ele tiver uma parecida. O kit iguala o volume do hook novo ao do validado (LUFS) sozinho.
- CTR baixo com venda boa = o corpo vende e a abertura não para o dedo: troque só os 3–6 s iniciais
  (gancho com tensão/teste/número, faixa de gancho desde 0 s, corte a cada ~1,3 s com `"ritmo": 1.3`).

## 5. Lote de roteiros

Grave em `<oferta>/07_roteiros/lote_NN.json` (próximo número livre):

```json
{
  "modo": "novos",
  "legenda": "variar",
  "narracao": {"motor": "edge", "voz": "pt-BR-AntonioNeural", "velocidade": "+8%"},
  "criativos": [
    {
      "id": "c01",
      "angulo": "curiosidade",
      "layout": "dividida",
      "hook": "Ninguém acredita que essa vela foi feita em casa.",
      "gancho_tela": "Ninguém acredita que foi feita em casa",
      "body": "Eu comecei com uma panela comum e um pote de vidro...",
      "cta_tela": "Link na bio",
      "midias": ["02_brutos/x.mp4", "04_imagens/y.jpg"],
      "midias_baixo": ["02_brutos/z.mp4"]
    }
  ]
}
```

Campos:
- `legenda`: `variar` | `caixa_roxa` | `palavra_amarela` (por criativo também aceita `legenda`).
- `narracao.motor`: `edge` (grátis) | `eleven` | `existente` (lê `05_audios/<id>.mp3` e transcreve).
  Vozes edge: `pt-BR-AntonioNeural`, `pt-BR-FranciscaNeural`, `pt-BR-ThalitaMultilingualNeural`,
  `pt-PT-DuarteNeural`, `pt-PT-RaquelNeural`. Alterne voz masculina/feminina entre criativos com `"voz"` no criativo.
- `layout`: `dividida` (tela dividida com linha vermelha, padrão) | `cheia`.
- `midias` / `midias_baixo`: opcionais. Sem elas, o kit sorteia de `02_brutos`, `04_imagens`, `03_apresentadora`
  (metade em cima, metade embaixo). Escolha manualmente quando houver mídia que combina com a fala.
- `ritmo`: segundos por corte (padrão 2.2). `sfx`: false desliga efeitos. `musica`: false desliga trilha.
- `gancho_duracao`: força quanto tempo a faixa de gancho fica na tela (padrão: até o fim do hook falado).
- `midias_gancho` (tela cheia): mídias usadas só durante o hook; o corpo usa só `midias`. Evita que a imagem
  de impacto do gancho (moeda, esqueleto) volte no meio do vídeo. O kit sempre corta no fim do hook.
- `faixa_fixa`: `{"texto": "117 Exercícios de\nMobilidade e Estabilidade\nApenas R$ 9,90", "cor": "#F97316",
  "cor_texto": "#111111", "desde": "fim_hook", "y": 0.07, "tamanho": 66, "caixa_alta": false}` — faixa que
  fica do fim do gancho até o fim (ou até o `fechamento`). `\n` quebra linha; só `texto` é obrigatório.
- `rotulos`: `["12 reps", "8 x lado", "30 seg"]` — rótulo pequeno sobre cada corte depois do hook, em ciclo.
- `encaixe`: `corte` (padrão, recorta o centro) | `desfoque` — em tela cheia, vídeo horizontal aparece numa
  faixa larga sobre ele mesmo desfocado, sem perder o movimento (bom para demonstração de exercício).
- `textos`: textos na tela com tempo — `[{"texto": "Teste 1", "desde": "palavra:primeiro", "ate": "proximo",
  "cor": "#7C3AED", "cor_texto": "#FFFFFF", "y": 0.26, "tamanho": 62, "cortar": true}]`.
  `desde`/`ate` aceitam segundos, `"fim_hook"`, `"fim"`, `"proximo"` (início do texto seguinte) ou
  `"palavra:X"` (início da palavra X na narração — `desde` procura em ordem; `ate` procura depois do início
  do próprio texto). Texto ancorado em palavra corta a imagem nesse instante (`cortar`, padrão true) e vai até
  o próximo; texto com `desde` em segundos vai até `"fim"`. Os cortes obrigatórios (fim do hook + textos)
  dividem o vídeo em seções e o `ritmo` corta só dentro delas — para uma lista, use `ritmo` alto (ex.: 12)
  e uma mídia por item em `midias`, na ordem.
- `textos[].midias`: mídias próprias da seção daquele texto (ex.: cada item de uma lista com suas 2–3
  imagens). Com isso o `ritmo` pode ser normal (~1.9) sem bagunçar qual imagem cai em cada item.
- Garanta que `midias` (corpo) tenha pelo menos tantas mídias quantos cortes: quando a lista acaba ela
  recomeça, e a imagem de dor do começo volta em cima da garantia/CTA. Termine a lista com imagens positivas.
- `gancho_estilo`: `"pergunta"` troca a faixa vermelha por um cartão branco de "PERGUNTA FREQUENTE"
  (título muda com `gancho_titulo`).
- `gancho_tela: false` desliga a faixa de gancho (útil na tela dividida com rótulos fixos em cada metade).


IDs: `c01…cNN` em criativos novos, `m01…` em modelagem, `v01…` em variações — únicos por oferta, porque
`05_audios/<id>` e `01_prontos/<id>.mp4` usam o id. Em lotes novos continue a numeração.

Mostre ao usuário uma tabela curta (id, ângulo, hook) e siga para a renderização, a menos que ele tenha pedido
para revisar antes.

## 6. Renderizar

```powershell
python "$KIT/montar.py" "<oferta>/07_roteiros/lote_NN.json"
```

**Rede:** a voz grátis (edge) e o ElevenLabs precisam de internet. Se o shell estiver em sandbox e a narração
falhar com `getaddrinfo failed` / `ClientConnectorDNSError`, rode o comando fora do sandbox. A voz grátis falha
de forma intermitente; o kit já tenta 5 vezes antes de desistir daquele criativo (os demais continuam).

Narra quem ainda não tem narração e monta tudo em `01_prontos/<id>.mp4` (1080x1920, 30 fps, H.264 + AAC),
mais `01_prontos/lote_NN_resumo.csv`. Lotes grandes demoram (≈20–60 s por criativo): rode em segundo plano.
`--ids c03,c07` refaz só alguns; `narrar.py --refazer --ids c03` regenera a voz.

## 7. Conferir e entregar

Extraia 1 quadro de 2–3 criativos e veja com Read:
`ffmpeg -ss 1.5 -i "01_prontos/c01.mp4" -frames:v 1 "_work/check_c01.jpg"`
Confira: faixa de gancho legível, legenda sincronizada e dentro da tela, cortes sem tela preta.
Entregue: pasta `01_prontos`, quantidade, e o CSV para nomear os anúncios no Gerenciador.
