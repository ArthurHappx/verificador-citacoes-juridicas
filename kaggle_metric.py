# -*- coding: utf-8 -*-
"""
Métrica oficial — Caça-Alucinações · BRACIS 2026 × Jusbrasil
Custom metric para Kaggle (community competition).

Contrato de Entrada e Saída v0.2:
  Passo 1  macro-F1 das 3 classes (real / inventada / incompleta), por nível,
           com a classe `real` exigindo id_canonico ∈ doc_ids do gabarito;
  Passo 2  penalidade do erro grave:  s = macroF1 · (1 − γ·τ), γ = 0,5,
           τ = fração das `inventada` do gabarito preditas como `real`;
  Passo 3  bônus de calibração (Brier): b = 0,10 · (1 − brier), sobre pares casados,
           aplicado como score = s · (1 + b);
  Passo 4  combinação dos níveis: score_final = (1·score_N1 + 2·score_N2) / 3
           — com o `score` do passo 3, já com o bônus embutido (§5.4).

Alinhamento predição × gabarito: IoU ≥ 0,5 em codepoints, matching 1-para-1
guloso por maior IoU. Gabarito sem par → FN; predição sem par → FP, exceto a
regra EXTRA: predição sem par que seja um *componente* de uma citação do
gabarito já casada (contida nela) é ignorada.

MATRIZ DE CONFUSÃO por classe c (§5.1) — a tabela completa:

  caso                                        TP        FP           FN
  ------------------------------------------- --------- ------------ ---------
  casou, classe c dos dois lados, link ok     tp[c]     —            —
  casou, classe c dos dois lados, link errado —         fp[real]     —
  casou, gabarito=c, predição=c' (c' ≠ c)     —         fp[c']       fn[c]
  predição sem par (espúria, não é EXTRA)     —         fp[predita]  —
  gabarito sem par (span não extraído)        —         —            fn[c]

Os dois pontos que costumam surpreender:
  · classe errada custa DUAS vezes — recall da classe esperada e precisão da
    predita —, porque cada citação do gabarito tem uma classe verdadeira só;
  · link errado em par `real`×`real` custa só precisão (FP sem FN).

FORMATO (transporte CSV do Kaggle — 1 linha por documento):
  sample_submission.csv:  documento_id, citacoes
  solution.csv:           documento_id, nivel, citacoes, Usage(Public|Private)

  Célula `citacoes` da SUBMISSÃO: citações separadas por "|", campos por ",":
      inicio,fim,classe,id_canonico,confianca
      · id_canonico: dígitos do doc_id Jusbrasil, ou "-" quando não houver;
      · confianca:   float em [0,1], ou "-" para não informar;
      · documento sem citações: célula vazia.
      Ex.: 1284,1302,real,2106313729,0.91|3401,3445,incompleta,-,0.80

  Célula `citacoes` da SOLUTION (gabarito): campos por ",":
      inicio,fim,classe,doc_ids
      · doc_ids: conjunto aceito, separado por ":" (ex.: 210631:210632), ou "-".

Assinatura exigida pelo Kaggle:
  score(solution: pd.DataFrame, submission: pd.DataFrame, row_id_column_name: str) -> float
Erros causados pelo participante devem levantar ParticipantVisibleError
(a mensagem é exibida a ele; demais exceções ficam ocultas).
"""

import numpy as np
import pandas as pd


class ParticipantVisibleError(Exception):
    pass


CLASSES = ("real", "inventada", "incompleta")
PESOS_NIVEL = {1: 1.0, 2: 2.0}   
GAMMA = 0.5                      # peso do erro grave
TETO_BONUS = 0.10                
IOU_MIN = 0.5                    # estrutural: é o que torna o guloso ótimo (_casar)
# fração da predição espúria que precisa cair dentro do gold 
# para ser considerado extração extra positiva. Aqui, nós "toleramos"
# extrações sem par no goldenset que casam com uma citação já casada anteriormente.
# Porém, extrações espúrias que não casam nada com o goldenset continuam FP
FRAC_EXTRA = 0.9                 


# ----------------------------------------------------------------------------- parsing

def _norm_id(v):
    """o id_canonico é o doc_id numérico do Jusbrasil. Normaliza os dois lados
    da comparação para que espaço em branco ou zero à esquerda — plausíveis na
    planilha do gabarito — não derrubem um link correto."""
    v = str(v).strip()
    return (v.lstrip("0") or "0") if v.isdigit() else v


def _int(v, doc, campo):
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ParticipantVisibleError(
            f"[{doc}] campo '{campo}' deve ser inteiro; recebido {v!r}.")


def _parse_submission_cell(cell, doc):
    """'inicio,fim,classe,id_canonico,confianca|...' -> list[dict]"""
    if cell is None or (isinstance(cell, float) and np.isnan(cell)):
        return []
    cell = str(cell).strip()
    if cell == "" or cell == "-":
        return []
    out = []
    for i, bloco in enumerate(cell.split("|")):
        bloco = bloco.strip()
        if not bloco:
            continue
        campos = [c.strip() for c in bloco.split(",")]
        if len(campos) != 5:
            raise ParticipantVisibleError(
                f"[{doc}] citação #{i + 1}: esperados 5 campos "
                f"(inicio,fim,classe,id_canonico,confianca); recebidos {len(campos)}: {bloco!r}.")
        inicio = _int(campos[0], doc, "inicio")
        fim = _int(campos[1], doc, "fim")
        if inicio < 0 or fim <= inicio:
            raise ParticipantVisibleError(
                f"[{doc}] citação #{i + 1}: span inválido ({inicio}, {fim}) — "
                f"exige 0 <= inicio < fim.")
        classe = campos[2].lower()
        if classe not in CLASSES:
            raise ParticipantVisibleError(
                f"[{doc}] citação #{i + 1}: classe {campos[2]!r} inválida; "
                f"use real | inventada | incompleta.")
        id_canonico = campos[3]
        if classe == "real":
            if id_canonico in ("", "-"):
                raise ParticipantVisibleError(
                    f"[{doc}] citação #{i + 1}: classificacao=real exige id_canonico.")
            if not id_canonico.isdigit():
                raise ParticipantVisibleError(
                    f"[{doc}] citação #{i + 1}: id_canonico deve conter só dígitos "
                    f"(doc_id Jusbrasil); recebido {id_canonico!r}.")
            id_canonico = _norm_id(id_canonico)
        else:
            id_canonico = None if id_canonico in ("", "-") else _norm_id(id_canonico)
        conf = campos[4]
        if conf in ("", "-"):
            confianca = None
        else:
            try:
                confianca = float(conf)
            except ValueError:
                raise ParticipantVisibleError(
                    f"[{doc}] citação #{i + 1}: confianca {conf!r} não é número.")
            if not (0.0 <= confianca <= 1.0):
                raise ParticipantVisibleError(
                    f"[{doc}] citação #{i + 1}: confianca {confianca} fora de [0, 1].")
        out.append(dict(inicio=inicio, fim=fim, classe=classe,
                        id_canonico=id_canonico, confianca=confianca))
    # §8: spans de citações diferentes com sobreposição acima do limite (duplicatas)
    for a in range(len(out)):
        for b in range(a + 1, len(out)):
            if _iou(out[a], out[b]) >= IOU_MIN:
                raise ParticipantVisibleError(
                    f"[{doc}] citações #{a + 1} e #{b + 1} se sobrepõem com IoU >= {IOU_MIN} "
                    f"(duplicata). Envie uma citação por span.")
    return out


def _parse_solution_cell(cell, doc):
    """'inicio,fim,classe,doc_ids' (doc_ids separados por ':') -> list[dict]

    Defeito no gabarito é defeito nosso, não do participante: os problemas aqui
    levantam ValueError (oculto pelo Kaggle), nunca ParticipantVisibleError.
    """
    if cell is None or (isinstance(cell, float) and np.isnan(cell)):
        return []
    cell = str(cell).strip()
    if cell == "" or cell == "-":
        return []
    out = []
    for bloco in cell.split("|"):
        bloco = bloco.strip()
        if not bloco:
            continue
        campos = [c.strip() for c in bloco.split(",")]
        inicio, fim = int(campos[0]), int(campos[1])
        classe = campos[2].lower()
        doc_ids = frozenset(_norm_id(x) for x in campos[3].split(":")
                            if x.strip() not in ("", "-"))
        if classe == "real" and not doc_ids:
            # sem doc_ids candidatos nenhuma predição consegue ser acerto pleno (§5.1)
            raise ValueError(
                f"[{doc}] gabarito: citação real em ({inicio}, {fim}) sem doc_ids. "
                f"A classe real exige o conjunto de doc_ids candidatos (§4).")
        out.append(dict(inicio=inicio, fim=fim, classe=classe, doc_ids=doc_ids))
    # O matching guloso só é ótimo com spans do gabarito disjuntos (ver _casar).
    for a in range(len(out)):
        for b in range(a + 1, len(out)):
            if _intersecao(out[a], out[b]) > 0:
                raise ValueError(
                    f"[{doc}] gabarito: citações ({out[a]['inicio']}, {out[a]['fim']}) e "
                    f"({out[b]['inicio']}, {out[b]['fim']}) se sobrepõem. O alinhamento "
                    f"guloso da §3 pressupõe citações esperadas disjuntas.")
    return out


# ----------------------------------------------------------------------------- alinhamento (§3)

def _intersecao(a, b):
    return max(0, min(a["fim"], b["fim"]) - max(a["inicio"], b["inicio"]))


def _iou(a, b):
    inter = _intersecao(a, b)
    if inter == 0:
        return 0.0
    uniao = (a["fim"] - a["inicio"]) + (b["fim"] - b["inicio"]) - inter
    return inter / uniao


def _contida(p, g, frac=FRAC_EXTRA):
    """A predição p é um *componente* da citação g?

    Essa é uma tolerância para granularidades extras, ou seja, o time que entrega
    'art. 1.021' e '§4º' onde o gabarito anota só o '§4º'. Exigir que a predição
    esteja essencialmente dentro do gold impede que a regra vire perdão para
    qualquer span espúrio que apenas encoste numa citação casada; Ou seja,
    extrações espúrias que não casam nada no goldenset seguem como FP.
    """
    largura = p["fim"] - p["inicio"]
    return largura > 0 and _intersecao(p, g) / largura >= frac


def _casar(golds, preds):
    """Matching 1-para-1 guloso por maior IoU (desempate determinístico).
    Retorna (pares [(gi, pi)], golds_sem_par [gi], preds_sem_par [pi]).

    O guloso aqui é *ótimo*, não uma aproximação, e isso depende de IOU_MIN >= 0,5:
    com esse limiar e citações do gabarito disjuntas (garantido em
    _parse_solution_cell), uma predição não consegue ter IoU >= 0,5 com dois golds
    ao mesmo tempo. Cada predição tem grau <= 1 do lado do gabarito, o único conflito
    possível é entre predições disputando o mesmo gold, e pegar a de maior IoU é a
    escolha ótima. Baixar IOU_MIN quebra a propriedade — aí seria preciso trocar por
    um matching de cardinalidade máxima (húngaro).
    """
    candidatos = []
    for gi, g in enumerate(golds):
        for pi, p in enumerate(preds):
            v = _iou(g, p)
            if v >= IOU_MIN:
                candidatos.append((-v, gi, pi))
    candidatos.sort()
    g_usado, p_usado, pares = set(), set(), []
    for _, gi, pi in candidatos:
        if gi in g_usado or pi in p_usado:
            continue
        g_usado.add(gi)
        p_usado.add(pi)
        pares.append((gi, pi))
    golds_sem_par = [gi for gi in range(len(golds)) if gi not in g_usado]
    preds_sem_par = [pi for pi in range(len(preds)) if pi not in p_usado]
    return pares, golds_sem_par, preds_sem_par


# ----------------------------------------------------------------------------- métrica (§5)

def _novo_acumulador():
    return dict(tp={c: 0 for c in CLASSES},
                fp={c: 0 for c in CLASSES},
                fn={c: 0 for c in CLASSES},
                suporte={c: 0 for c in CLASSES},
                tau_num=0, tau_den=0, brier_termos=[])


def _acumular_documento(acc, golds, preds):
    pares, golds_sem_par, preds_sem_par = _casar(golds, preds)

    for g in golds:
        acc["suporte"][g["classe"]] += 1
        if g["classe"] == "inventada":
            acc["tau_den"] += 1

    for gi, pi in pares:
        g, p = golds[gi], preds[pi]
        cg, cp = g["classe"], p["classe"]
        if cg == cp:
            if cg == "real":
                link_ok = p["id_canonico"] in g["doc_ids"]
                if link_ok:
                    acc["tp"]["real"] += 1
                    y = 1
                else:
                    # real com doc_id errado -> FP de real (sem FN), y = 0
                    acc["fp"]["real"] += 1
                    y = 0
            else:
                acc["tp"][cg] += 1
                y = 1
        else:
            # classe errada custa duas vezes — recall da classe esperada e
            # precisão da predita. O span ter sido extraído não salva o recall de cg:
            # a citação esperada continua não tendo sido reconhecida como cg.
            acc["fn"][cg] += 1
            acc["fp"][cp] += 1
            y = 0
            if cg == "inventada" and cp == "real":
                acc["tau_num"] += 1   # o erro grave (§5.2)
        if p["confianca"] is not None:
            acc["brier_termos"].append((p["confianca"] - y) ** 2)

    for gi in golds_sem_par:
        acc["fn"][golds[gi]["classe"]] += 1   # não extraído -> erro de recall

    matched_golds = [golds[gi] for gi, _ in pares]
    for pi in preds_sem_par:
        p = preds[pi]
        # §6 EXTRA: componente contido numa citação do gabarito que já casou -> ignorada
        extra = any(_contida(p, g) for g in matched_golds)
        if not extra:
            acc["fp"][p["classe"]] += 1       # extração espúria -> erro de precisão


def _score_nivel(acc):
    f1s = {}
    for c in CLASSES:
        if acc["suporte"][c] == 0:
            continue                          # classe sem ocorrência fica fora da média
        tp, fp, fn = acc["tp"][c], acc["fp"][c], acc["fn"][c]
        denom = 2 * tp + fp + fn
        f1s[c] = (2 * tp / denom) if denom > 0 else 0.0
    if not f1s:
        return None
    macro_f1 = float(np.mean(list(f1s.values())))
    tau = acc["tau_num"] / acc["tau_den"] if acc["tau_den"] > 0 else 0.0
    s = macro_f1 * (1.0 - GAMMA * tau)
    if acc["brier_termos"]:
        brier = float(np.mean(acc["brier_termos"]))
        b = max(0.0, min(TETO_BONUS, TETO_BONUS * (1.0 - brier)))
    else:
        b = 0.0                               # sem confianca: sem bônus, sem punição
    return dict(macro_f1=macro_f1, f1_por_classe=f1s, tau=tau, s=s, b=b,
                score=s * (1.0 + b))


def avaliar(solution: pd.DataFrame, submission: pd.DataFrame,
            row_id: str = "documento_id") -> dict:
    """Avaliação completa; retorna detalhes por nível e o score final."""
    sol = solution.copy()
    sub = submission.copy()
    for df, nome, obrig in ((sol, "solution", {row_id, "nivel", "citacoes"}),
                            (sub, "submission", {row_id, "citacoes"})):
        faltam = obrig - set(df.columns)
        if faltam:
            raise ParticipantVisibleError(
                f"Colunas ausentes no arquivo de {nome}: {sorted(faltam)}.")
    sub = sub.drop_duplicates(subset=[row_id], keep="first")

    sol_idx = sol.set_index(row_id)
    sub_idx = sub.set_index(row_id)
    faltando = sol_idx.index.difference(sub_idx.index)
    if len(faltando) > 0:
        raise ParticipantVisibleError(
            f"Submissão sem linha para {len(faltando)} documento(s), "
            f"ex.: {list(faltando[:3])}. Envie uma linha por documento "
            f"(célula vazia se não houver citações).")

    acumuladores = {}
    for doc, linha in sol_idx.iterrows():
        nivel = int(linha["nivel"])
        golds = _parse_solution_cell(linha["citacoes"], doc)
        preds = _parse_submission_cell(sub_idx.loc[doc, "citacoes"], doc)
        acc = acumuladores.setdefault(nivel, _novo_acumulador())
        _acumular_documento(acc, golds, preds)

    niveis = {}
    for nivel, acc in sorted(acumuladores.items()):
        r = _score_nivel(acc)
        if r is not None:
            niveis[nivel] = r
    if not niveis:
        raise ParticipantVisibleError("Nenhuma citação avaliável no conjunto.")

    peso_total = sum(PESOS_NIVEL.get(n, 1.0) for n in niveis)
    score_final = sum(PESOS_NIVEL.get(n, 1.0) * r["score"]
                      for n, r in niveis.items()) / peso_total
    return dict(score_final=float(score_final), niveis=niveis)


def score(solution: pd.DataFrame, submission: pd.DataFrame,
          row_id_column_name: str) -> float:
    """Ponto de entrada exigido pelo Kaggle."""
    if "Usage" in solution.columns:              # o Kaggle já filtra por Usage;
        solution = solution.drop(columns=["Usage"])   # remover se vier junto
    return avaliar(solution, submission, row_id=row_id_column_name)["score_final"]
