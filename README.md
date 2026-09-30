# Verificador de Citações Jurídicas

Verificador offline de citações jurídicas no contexto do direito brasileiro, desenvolvido para analisar textos jurídicos em língua portuguesa, especialmente pareceres, petições e memorandos produzidos ou auxiliados por inteligência artificial. O software localiza cada citação, extrai seus identificadores, consulta uma base canônica e a classifica como **real**, **inventada** ou **incompleta**.

> **Quer apenas executar?** Consulte o [guia de execução rápida](FAST_RUN.md).

O projeto foi desenvolvido como solução para o [desafio técnico do Jusbrasil no BRACIS 2026](https://challenge-bracis.production.jusbrasil.com.br/). O problema proposto parte de um risco concreto do uso de modelos generativos no Direito: referências inexistentes podem ser apresentadas como verdadeiras, enquanto referências vagas podem impedir qualquer verificação.

## O que o software verifica

Para cada documento `.txt`, o pipeline identifica referências a acórdãos,
súmulas e dispositivos legais e produz uma decisão auditável:

| Classe | Interpretação |
|---|---|
| `real` | A citação tem identificadores suficientes e resolve para exatamente um registro da base canônica. A saída inclui seu `id_canonico`. |
| `inventada` | Há identificadores suficientes para consulta, mas nenhum registro correspondente foi encontrado na cobertura da base. |
| `incompleta` | Faltam dados para uma consulta confiável ou a consulta preserva mais de um candidato sem critério seguro de desempate. |

Uma citação classificada como `real` é real em relação à cobertura do SQLite fornecido. O sistema não consulta bases vivas e não afirma que uma referência inexistente nesse recorte nunca tenha existido em outra fonte ou período.

## Como funciona

O fluxo é composto por seis etapas:

1. **Identificação:** um BERTimbau ajustado para NER encontra spans `ACOR`, `SUM` e `LEG` no texto original.
2. **Pós-processamento:** regras conservadoras consolidam janelas e tratam fragmentações ou superfícies jurídicas de alta precisão.
3. **Extração e normalização:** extratores recuperam número, tribunal, classe processual, UF, ano, relator, diploma e artigo, incluindo variantes comuns de OCR.
4. **Indexação canônica:** o cabeçalho de cada registro do SQLite é analisado uma vez e transformado em tabelas indexadas por identificadores. O texto integral não é usado indiscriminadamente como prova de identidade, pois um acórdão pode apenas citar outro.
5. **Recuperação e decisão:** consultas completas e relaxamentos controlados preservam todos os candidatos. Cardinalidade, suficiência e conflitos determinam a classificação final.
6. **Saída:** um JSON enriquecido é salvo por documento e o conversor oficial gera o CSV de submissão.

## Requisitos

- Docker 24 ou posterior;
- NVIDIA Container Toolkit para execução em GPU;
- espaço para a imagem, o checkpoint e o índice gerado;
- internet apenas na preparação, para obter a imagem base, dependências e o
  asset fixo do modelo.

Depois de construída, a solução executa sem internet e não usa APIs externas nem baixa artefatos do Hugging Face Hub.

## Obtenção dos pesos

Os pesos não ficam no histórico Git. O checkpoint aprovado é publicado como asset de uma GitHub Release fixa, configurada em `model-release.env` e verificada por SHA-256:

```bash
./scripts/download_model.sh
```

Em repositório privado, use um token com permissão somente de leitura:

```bash
GITHUB_TOKEN=... ./scripts/download_model.sh
```

Também é possível baixar o asset de forma autenticada e validar o arquivo localmente:

```bash
gh release download model-v1.0.0 \
  --pattern 'bertimbau-citations-v1.0.0.tar.gz'
./scripts/download_model.sh bertimbau-citations-v1.0.0.tar.gz
```

Consulte [MODEL_CARD.md](MODEL_CARD.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) e [LICENSE](LICENSE) para proveniência, atribuições, limitações e licenciamento.

## Execução

O ponto de entrada único recebe o SQLite original, a pasta dos documentos e o caminho exato do CSV de saída:

```bash
bash run.sh <caminho_db> <pasta_txt> <arquivo_saida.csv>
```

Exemplo:

```bash
bash run.sh \
  /dados/base.db \
  /dados/txt \
  /resultado/submission.csv \
  --device cuda
```

O índice `canonical_index.sqlite` é criado automaticamente ao lado do CSV. Um índice existente somente é reutilizado se sua versão e o SHA-256 da base forem compatíveis. Todas as opções podem ser consultadas com:

```bash
bash run.sh --help
```

### Saídas

Além do CSV solicitado, a pasta de saída recebe:

```text
resultado/
├── submission.csv
├── canonical_index.sqlite
├── run_summary.json
└── enriched_json/
    ├── documento_001.json
    └── ...
```

Cada JSON enriquecido registra spans, dados extraídos, alertas, tentativas de consulta, lista de `id_canonicos` candidatos, regra de decisão, confiança e eventuais erros. Falhas são isoladas por documento ou citação sempre que isso é seguro.

## Execução com Docker

Depois de baixar e verificar os pesos:

```bash
docker build -t legal-citation-verifier:1.0.0 .
mkdir -p output

docker run --rm --network none --gpus all \
  -v "/caminho/base.db:/input/base.db:ro" \
  -v "/caminho/txt:/input/txt:ro" \
  -v "$PWD/output:/output" \
  legal-citation-verifier:1.0.0 \
  /input/base.db /input/txt /output/submission.csv --device cuda
```

Para uma verificação funcional em CPU, remova `--gpus all` e use `--device cpu`. O banco de entrada é montado somente para leitura; índice e resultados são gravados em `/output`.

## Contrato de entrada

O diretório de entrada deve conter um ou mais arquivos `.txt` UTF-8. O nome sem extensão se torna o `documento_id`.

O SQLite deve conter uma tabela `documentos` compatível com o formato do desafio, incluindo:

| Coluna | Função |
|---|---|
| `id` | Identificador canônico devolvido para uma citação real. |
| `documento_id` | Identificador interno do documento na base. |
| `tribunal`, `ano`, `relator` | Metadados de decisões judiciais. |
| `natureza` | `acordao`, `sumula` ou `dispositivo`. |
| `tipo` | `jurisprudencia` ou `lei`. |
| `texto` | Conteúdo usado para derivar o cabeçalho canônico. |

O SQLite original é aberto em modo somente leitura. O enriquecimento é salvo exclusivamente no índice lateral.

## Reprodutibilidade e testes

O seed padrão é `42`. A inferência não usa amostragem, o modelo opera em modo de avaliação e o ponto de entrada desativa otimizações não determinísticas relevantes. A imagem base e as dependências principais estão fixadas.

Execute os testes com:

```bash
python3 -m unittest discover -v -s tests -p 'test_*.py'
python3 -m unittest discover -v -s extraction/testes -p 'test_*.py'
```

Os testes de integração e regressão usam a base, o índice e o gabarito de desenvolvimento quando esses artefatos estão presentes; em um clone público sem os dados, eles são ignorados explicitamente. O teste final recomendado é executar a imagem com `--network none` e validar o CSV produzido.

## Estrutura do projeto

```text
├── identifier/                 # NER, inferência em janelas e pós-processamento
├── extraction/                 # extração e normalização de identificadores
├── retrieval/                  # construção do índice, busca e decisão
├── pipeline/                   # fachada, contrato enriquecido e validação
├── data/dicionario_classes.json
├── scripts/                    # empacotamento e download verificado do modelo
├── tests/                      # testes unitários, integração e regressão
├── run.py / run.sh             # ponto de entrada único
├── Dockerfile
└── json_to_submission.py       # conversor fornecido pelo desafio
```

## Limitações

- A conclusão sobre existência é limitada à cobertura da base recebida.
- Ruído de OCR severo ou formatos jurídicos fora do domínio de treinamento podem causar omissões ou spans imprecisos.
- As regras de pós-processamento priorizam precisão e podem deixar referências vagas como incompletas.
- A confiança é uma estimativa operacional do pipeline e não substitui revisão jurídica humana.

## Autores

- [Arthur Félix](https://github.com/ArthurHappx)
- [Daniel Damião](https://github.com/DanielPDamiao)
- [Daniele Oliveira](https://github.com/danieleolivs)
- [Andrey Kauã](https://github.com/Andrey-Kaua)

## Como citar

Os metadados de citação estão disponíveis em [CITATION.cff](CITATION.cff). Em interfaces compatíveis, use a opção **Cite this repository**. A citação do BERTimbau, modelo-base do identificador, permanece registrada separadamente em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Licença

O código e os pesos ajustados são disponibilizados sob a licença MIT, sujeitos aos avisos e às licenças de terceiros. Essa licença não concede direitos sobre bases, documentos ou conjuntos de dados de terceiros, que não acompanham o repositório.
