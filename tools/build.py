#!/usr/bin/env python3
"""Build derived data, chart fragments and diagrams for the static landing page.

Reads only the JSON copies in ``data/``, checks the published numbers against the
expected values, writes small derived JSON files and rewrites the blocks of
``index.html`` delimited by ``<!-- gerado:NAME -->`` and ``<!-- /gerado:NAME -->``.

Usage: python3 tools/build.py [--check]
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

LOG = logging.getLogger("build")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMG = ROOT / "assets" / "img"
INDEX = ROOT / "index.html"

FAIXAS: tuple[str, ...] = ("C", "C+", "B", "B+", "A")
FAIXA_CLASS = {"C": "c", "C+": "cp", "B": "b", "B+": "bp", "A": "a"}
FAIXA_FLOOR = {"C": 0.0, "C+": 0.50, "B": 0.60, "B+": 0.75, "A": 0.90}
TOTAL_MUNICIPIOS = 644
ANO_FOCO = "2024"


@dataclass(frozen=True)
class Indice:
    key: str
    code: str
    name: str
    weight: int


INDICES: tuple[Indice, ...] = (
    Indice("iplanejamento", "i-Plan", "Planejamento", 20),
    Indice("ifiscal", "i-Fiscal", "Gestão fiscal", 20),
    Indice("ieduc", "i-Educ", "Educação", 20),
    Indice("isaude", "i-Saúde", "Saúde", 20),
    Indice("iamb", "i-Amb", "Meio ambiente", 10),
    Indice("icidade", "i-Cidade", "Cidades protegidas", 5),
    Indice("igov", "i-Gov TI", "Governança de TI", 5),
)
WEIGHT_BY_CODE = {i.code: i.weight for i in INDICES}


@dataclass(frozen=True)
class Item:
    code: str
    title: str
    points: int
    tipo: str
    out_of: int | None = None
    municipios: int | None = None
    situacao: str = ""

    @property
    def pp(self) -> float:
        """Approximate weight of the item in the IEG-M, in percentage points."""
        return self.points / 1000 * WEIGHT_BY_CODE[self.code]


MESA: tuple[Item, ...] = (
    Item(
        "i-Plan",
        "Pontualidade na entrega das peças de planejamento",
        150,
        "processo",
        municipios=521,
        situacao="entregaram fora do prazo",
    ),
    Item(
        "i-Cidade",
        "Mapeamento das principais ameaças do território",
        200,
        "investimento",
        municipios=248,
        situacao="responderam Não",
    ),
    Item(
        "i-Saúde",
        "Controle do estoque de medicamentos no sistema Hórus",
        40,
        "processo",
        municipios=469,
        situacao="usam sistema próprio e ganham zero",
    ),
    Item(
        "i-Cidade",
        "Estudo da estrutura de escolas e UBS para abrigar a população em desastres",
        100,
        "investimento",
        municipios=355,
        situacao="ficaram na pior opção",
    ),
    Item(
        "i-Gov TI",
        "Política de segurança da informação formalmente instituída",
        50,
        "norma",
        municipios=355,
        situacao="não têm",
    ),
    Item("i-Cidade", "PLANCON, plano de contingência de Defesa Civil", 50, "norma", municipios=262, situacao="não têm"),
    Item(
        "i-Gov TI",
        "PDTIC, plano diretor de tecnologia da informação, vigente",
        40,
        "norma",
        municipios=408,
        situacao="não possuem",
    ),
)

SUZANO_PERDAS: tuple[Item, ...] = (
    Item("i-Plan", "Peças de planejamento entregues fora do prazo", 150, "processo"),
    Item("i-Educ", "Sem pesquisa de demanda por vaga em creche", 50, "processo"),
    Item("i-Educ", "Sem pesquisa de demanda por vaga na pré-escola", 50, "processo"),
    Item("i-Educ", "Sem pesquisa de demanda por vaga nos anos iniciais", 20, "processo"),
    Item("i-Amb", "Coleta seletiva", 90, "investimento", out_of=100),
    Item("i-Saúde", "Estoque de medicamentos controlado fora do Hórus", 40, "processo"),
    Item("i-Fiscal", "Balancetes rejeitados", 25, "processo"),
    Item("i-Amb", "Metas do plano de resíduos", 40, "investimento", out_of=50),
)

TIPO_LABEL = {
    "norma": "Norma",
    "processo": "Processo",
    "investimento": "Investimento",
}

EXEMPLO = "Suzano"
VIZINHOS: tuple[str, ...] = (
    "Arujá",
    "Biritiba-Mirim",
    "Ferraz de Vasconcelos",
    "Guararema",
    "Itaquaquecetuba",
    "Mogi das Cruzes",
    "Salesópolis",
    "Santa Isabel",
    "Suzano",
)

EXPECTED = {
    "dist_2024": {"C": 283, "C+": 261, "B": 97, "B+": 3, "A": 0},
    "c_2024": {
        "i-Plan": 533,
        "i-Amb": 415,
        "i-Cidade": 413,
        "i-Gov TI": 320,
        "i-Educ": 169,
        "i-Fiscal": 122,
        "i-Saúde": 78,
    },
    "media_ponderada_2024": "0.508",
    "suzano_hist": {
        "2014": "B",
        "2015": "B",
        "2016": "B",
        "2017": "C+",
        "2018": "C+",
        "2019": "C+",
        "2020": "C",
        "2021": "C+",
        "2022": "C+",
        "2023": "C+",
        "2024": "B",
    },
    "suzano_2024": {
        "i-Plan": "B",
        "i-Fiscal": "B",
        "i-Educ": "C+",
        "i-Saúde": "B",
        "i-Amb": "C+",
        "i-Cidade": "B+",
        "i-Gov TI": "B+",
    },
    "vizinhos_2024": {
        "Arujá": "C+",
        "Biritiba-Mirim": "C",
        "Ferraz de Vasconcelos": "B",
        "Guararema": "B",
        "Itaquaquecetuba": "C",
        "Mogi das Cruzes": "C",
        "Salesópolis": "C",
        "Santa Isabel": "C",
        "Suzano": "B",
    },
}


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def num(value: float, decimals: int = 0) -> str:
    """Format a number the Brazilian way: dot for thousands, comma for decimals."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def pp_text(value: float) -> str:
    decimals = 1 if abs(round(value * 10) - value * 10) < 1e-9 else 2
    return num(value, decimals)


def pct(value: float, decimals: int = 1) -> str:
    return f"{num(value * 100, decimals)}%"


def faixa_of(score: float) -> str:
    for faixa in reversed(FAIXAS):
        if score >= FAIXA_FLOOR[faixa]:
            return faixa
    return "C"


class Dataset:
    """Official bands per municipality and statewide means, as published by the TCESP panel."""

    def __init__(self, faixas_path: Path, media_path: Path) -> None:
        self.faixas: dict[str, list[dict]] = json.loads(faixas_path.read_text(encoding="utf-8"))
        media_raw = json.loads(media_path.read_text(encoding="utf-8"))
        cols = [c["colName"] for c in media_raw["metadata"]]
        self.media: dict[str, dict[str, float]] = {}
        for row in media_raw["resultset"]:
            rec = dict(zip(cols, row))
            self.media[str(rec["exercicio_ref"])] = {i.key: float(rec[i.key]) for i in INDICES}
        self.anos = sorted(self.faixas)
        LOG.info("loaded %d years of bands and %d years of means", len(self.anos), len(self.media))

    def distribution(self, ano: str, key: str = "iegm") -> dict[str, int]:
        counts = Counter(r[key] for r in self.faixas[ano])
        unknown = set(counts) - set(FAIXAS)
        if unknown:
            raise ValueError(f"unexpected band labels in {ano}/{key}: {unknown}")
        return {f: counts.get(f, 0) for f in FAIXAS}

    def distribution_by_year(self) -> dict[str, dict[str, int]]:
        return {ano: self.distribution(ano) for ano in self.anos}

    def c_by_index(self, ano: str) -> dict[str, int]:
        return {i.code: self.distribution(ano, i.key)["C"] for i in INDICES}

    def weighted_mean(self, ano: str) -> float:
        return sum(self.media[ano][i.key] * i.weight / 100 for i in INDICES)

    def transitions(self, before: str, after: str) -> dict[str, int]:
        order = {f: n for n, f in enumerate(FAIXAS)}
        prev = {r["codigo_municipio"]: r["iegm"] for r in self.faixas[before]}
        result = {"subiram": 0, "mantiveram": 0, "caíram": 0}
        for rec in self.faixas[after]:
            delta = order[rec["iegm"]] - order[prev[rec["codigo_municipio"]]]
            key = "subiram" if delta > 0 else "caíram" if delta < 0 else "mantiveram"
            result[key] += 1
        return result

    def municipio(self, nome: str, ano: str) -> dict:
        matches = [r for r in self.faixas[ano] if r["nome"] == nome]
        if len(matches) != 1:
            raise LookupError(f"{nome!r} found {len(matches)} times in {ano}")
        return matches[0]

    def history(self, nome: str) -> dict[str, str]:
        return {ano: self.municipio(nome, ano)["iegm"] for ano in self.anos}

    def bands_by_index(self, nome: str, ano: str) -> dict[str, str]:
        rec = self.municipio(nome, ano)
        return {i.code: rec[i.key] for i in INDICES}


class Verifier:
    """Fails the build when a derived number diverges from the checked reference."""

    def __init__(self, ds: Dataset) -> None:
        self.ds = ds
        self.errors: list[str] = []

    def expect(self, label: str, got: object, want: object) -> None:
        if got != want:
            self.errors.append(f"{label}: got {got!r}, expected {want!r}")
        else:
            LOG.info("ok %s", label)

    def run(self) -> None:
        ds = self.ds
        self.expect("anos-base", ds.anos, [str(a) for a in range(2014, 2025)])
        for ano in ds.anos:
            self.expect(f"municipios {ano}", len(ds.faixas[ano]), TOTAL_MUNICIPIOS)
        self.expect("distribuicao 2024", ds.distribution(ANO_FOCO), EXPECTED["dist_2024"])
        self.expect("C por indice 2024", ds.c_by_index(ANO_FOCO), EXPECTED["c_2024"])
        self.expect("media ponderada 2024", f"{ds.weighted_mean(ANO_FOCO):.3f}", EXPECTED["media_ponderada_2024"])
        self.expect("nenhum A", sum(ds.distribution(a)["A"] for a in ds.anos), 0)
        self.expect("historico Suzano", ds.history(EXEMPLO), EXPECTED["suzano_hist"])
        self.expect("Suzano 2024", ds.bands_by_index(EXEMPLO, ANO_FOCO), EXPECTED["suzano_2024"])
        self.expect(
            "vizinhos 2024", {n: ds.municipio(n, ANO_FOCO)["iegm"] for n in VIZINHOS}, EXPECTED["vizinhos_2024"]
        )
        self.expect("soma das perdas de Suzano (p.p.)", round(sum(i.pp for i in SUZANO_PERDAS), 2), 8.0)
        if self.errors:
            for err in self.errors:
                LOG.error(err)
            raise SystemExit(1)


class Renderer:
    """HTML fragments injected in index.html."""

    def __init__(self, ds: Dataset) -> None:
        self.ds = ds

    @staticmethod
    def chip(faixa: str, extra: str = "") -> str:
        return f'<span class="fx f-{FAIXA_CLASS[faixa]}{extra}">{esc(faixa)}</span>'

    @staticmethod
    def legend() -> str:
        items = "".join(
            f'<li><span class="sw f-{FAIXA_CLASS[f]}" aria-hidden="true"></span>{esc(f)}</li>' for f in FAIXAS
        )
        return f'<ul class="legend" aria-label="Legenda das faixas">{items}</ul>'

    def faixas_por_ano(self) -> str:
        dist = self.ds.distribution_by_year()
        rows: list[str] = []
        labelled = {self.ds.anos[0], self.ds.anos[-1]}
        for ano, counts in dist.items():
            summary = ", ".join(f"{f}: {counts[f]}" for f in FAIXAS)
            segs: list[str] = []
            for faixa in FAIXAS:
                n = counts[faixa]
                if n == 0:
                    continue
                share = n / TOTAL_MUNICIPIOS
                label = f'<span class="seg-v">{n}</span>' if ano in labelled and share >= 0.08 else ""
                segs.append(
                    f'<span class="seg f-{FAIXA_CLASS[faixa]}" style="flex-grow:{n}" '
                    f'data-faixa="{esc(faixa)}" data-n="{n}">{label}</span>'
                )
            data = esc(json.dumps(counts, ensure_ascii=False))
            rows.append(
                f'<div class="stack-row" tabindex="0" role="img" data-ano="{ano}" data-counts="{data}" '
                f'aria-label="Ano-base {ano}. {esc(summary)}.">'
                f'<span class="stack-year">{ano}</span>'
                f'<span class="stack-bar">{"".join(segs)}</span></div>'
            )
        head = "".join(f'<th scope="col">{esc(f)}</th>' for f in FAIXAS)
        body = "".join(
            f'<tr><th scope="row">{ano}</th>'
            + "".join(f"<td>{counts[f]}</td>" for f in FAIXAS)
            + f"<td>{sum(counts.values())}</td></tr>"
            for ano, counts in dist.items()
        )
        return (
            self.legend()
            + '<div class="stack-chart" data-tooltip="stack">'
            + "".join(rows)
            + '<div class="stack-axis" aria-hidden="true"><span>0</span><span>161</span>'
            "<span>322</span><span>483</span><span>644</span></div></div>"
            + '<details class="table-view"><summary>Ver os números em tabela</summary>'
            '<div class="table-scroll"><table class="tbl num"><caption>Municípios por faixa do IEG-M e ano-base</caption>'
            f'<thead><tr><th scope="col">Ano-base</th>{head}<th scope="col">Total</th></tr></thead>'
            f"<tbody>{body}</tbody></table></div></details>"
        )

    def c_por_indice(self) -> str:
        counts = self.ds.c_by_index(ANO_FOCO)
        names = {i.code: i.name for i in INDICES}
        ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        rows = []
        for code, n in ordered:
            share = n / TOTAL_MUNICIPIOS
            rows.append(
                f'<div class="hbar-row" tabindex="0" role="img" data-tip-title="{esc(code)}, {esc(names[code])}" '
                f'data-tip-value="{n} de {TOTAL_MUNICIPIOS} em C ({pct(share)})" '
                f'aria-label="{esc(code)}: {n} de {TOTAL_MUNICIPIOS} municípios em C">'
                f'<span class="hbar-label"><b>{esc(code)}</b><small>{esc(names[code])}</small></span>'
                f'<span class="hbar-track"><span class="hbar-fill f-c" style="width:{share * 100:.2f}%"></span>'
                f'<span class="hbar-val" style="left:{share * 100:.2f}%">{n}</span></span></div>'
            )
        body = "".join(
            f'<tr><th scope="row">{esc(code)}</th><td>{n}</td><td>{pct(n / TOTAL_MUNICIPIOS)}</td></tr>'
            for code, n in ordered
        )
        return (
            '<div class="hbar-chart" data-tooltip="simple">'
            + "".join(rows)
            + '<div class="hbar-axis" aria-hidden="true"><span>0</span><span>322</span><span>644 municípios</span></div></div>'
            + '<details class="table-view"><summary>Ver os números em tabela</summary>'
            '<div class="table-scroll"><table class="tbl num"><caption>Municípios em C por índice, ano-base 2024</caption>'
            '<thead><tr><th scope="col">Índice</th><th scope="col">Em C</th><th scope="col">Parcela de 644</th></tr></thead>'
            f"<tbody>{body}</tbody></table></div></details>"
        )

    def _panel(self, title: str, subtitle: str, series: list[float], highlight: bool = False) -> str:
        lo, hi = 0.2, 0.9
        anos = self.ds.anos

        def y(v: float) -> float:
            return (hi - v) / (hi - lo) * 100

        def x(n: int) -> float:
            return n / (len(series) - 1) * 100

        bands = [("c", lo, 0.5, "C"), ("cp", 0.5, 0.6, "C+"), ("b", 0.6, 0.75, "B"), ("bp", 0.75, hi, "B+")]
        rects = "".join(
            f'<rect class="band f-{cls}" x="0" y="{y(top):.3f}" width="100" height="{y(bottom) - y(top):.3f}"/>'
            for cls, bottom, top, _ in bands
        )
        band_labels = "".join(
            f'<span class="sm-band" style="top:{(y(top) + y(bottom)) / 2:.2f}%">{esc(label)}</span>'
            for _, bottom, top, label in bands
        )
        ticks = "".join(
            f'<span class="sm-tick" style="top:{y(v):.2f}%">{int(v * 100)}</span>' for v in (0.5, 0.6, 0.75)
        )
        points = " ".join(f"{x(n):.3f},{y(v):.3f}" for n, v in enumerate(series))
        first, last = series[0], series[-1]
        data = esc(json.dumps([round(v, 4) for v in series]))
        years = esc(json.dumps(anos))
        delta = (last - first) * 100
        sign = "+" if delta > 0 else "−"
        aria = (
            f"{title}, {subtitle}: {pct(first)} em {anos[0]} e {pct(last)} em {anos[-1]}, "
            f"faixa de referência {faixa_of(last)} no último ano."
        )
        return (
            f'<figure class="sm{" sm-hl" if highlight else ""}">'
            f'<figcaption><span class="sm-name">{esc(title)}</span><span class="sm-sub">{esc(subtitle)}</span></figcaption>'
            f'<div class="sm-vals"><span><small>{anos[0]}</small> {pct(first)}</span>'
            f'<span class="sm-last"><small>{anos[-1]}</small> {pct(last)}</span>'
            f'<span class="sm-delta">{sign}{num(abs(delta), 1)} p.p.</span></div>'
            f'<div class="sm-plot" tabindex="0" role="img" aria-label="{esc(aria)}" data-series="{data}" data-years="{years}" data-name="{esc(title)}">'
            f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
            f'{rects}<polyline class="sm-line" points="{points}"/></svg>'
            f"{band_labels}{ticks}"
            f'<span class="sm-dot" style="left:100%;top:{y(last):.2f}%"></span>'
            f'<span class="sm-cross" hidden></span></div>'
            f'<div class="sm-x" aria-hidden="true"><span>{anos[0]}</span><span>{anos[-1]}</span></div>'
            "</figure>"
        )

    def medias(self) -> str:
        anos = self.ds.anos
        panels = [self._panel(i.code, i.name, [self.ds.media[a][i.key] for a in anos]) for i in INDICES]
        panels.append(
            self._panel("IEG-M", "média ponderada pelos pesos", [self.ds.weighted_mean(a) for a in anos], True)
        )
        head = "".join(f'<th scope="col">{esc(i.code)}</th>' for i in INDICES)
        body = "".join(
            f'<tr><th scope="row">{a}</th>'
            + "".join(f"<td>{num(self.ds.media[a][i.key], 3)}</td>" for i in INDICES)
            + f"<td>{num(self.ds.weighted_mean(a), 3)}</td></tr>"
            for a in anos
        )
        return (
            '<div class="sm-grid" data-tooltip="series">'
            + "".join(panels)
            + "</div>"
            + '<details class="table-view"><summary>Ver os números em tabela</summary>'
            '<div class="table-scroll"><table class="tbl num"><caption>Média estadual por índice (0 a 1) e média ponderada do IEG-M</caption>'
            f'<thead><tr><th scope="col">Ano-base</th>{head}<th scope="col">IEG-M ponderado</th></tr></thead>'
            f"<tbody>{body}</tbody></table></div></details>"
        )

    def mesa(self) -> str:
        rows = []
        for item in MESA:
            assert item.municipios is not None
            share = item.municipios / TOTAL_MUNICIPIOS
            rows.append(
                "<tr>"
                f'<td data-label="Índice"><span class="code">{esc(item.code)}</span></td>'
                f'<th scope="row" data-label="Item">{esc(item.title)}</th>'
                f'<td data-label="Vale" class="n">{item.points} pontos</td>'
                f'<td data-label="Municípios sem os pontos" class="mesa-n">'
                f'<span class="mini" aria-hidden="true"><span style="width:{share * 100:.1f}%"></span></span>'
                f"<span><b>{item.municipios}</b> de {TOTAL_MUNICIPIOS} {esc(item.situacao)}</span></td>"
                f'<td data-label="No IEG-M" class="n">{pp_text(item.pp)} p.p.</td>'
                f'<td data-label="Correção"><span class="tipo t-{item.tipo}">{TIPO_LABEL[item.tipo]}</span></td>'
                "</tr>"
            )
        return (
            '<div class="table-scroll"><table class="tbl mesa">'
            "<caption>Itens com mais municípios sem pontuação, ordenados pelo peso no IEG-M</caption>"
            '<thead><tr><th scope="col">Índice</th><th scope="col">Item</th><th scope="col">Vale</th>'
            '<th scope="col">Municípios sem os pontos</th><th scope="col">No IEG-M</th>'
            '<th scope="col">Correção</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )

    @staticmethod
    def checklist(items: tuple[Item, ...], name: str, show_count: bool) -> str:
        out = []
        for n, item in enumerate(items):
            pts = f"{item.points} de {item.out_of}" if item.out_of else f"{item.points}"
            extra = (
                f'<span class="ck-meta">{item.municipios} de {TOTAL_MUNICIPIOS} municípios {esc(item.situacao)}</span>'
                if show_count and item.municipios
                else ""
            )
            out.append(
                f'<li><label class="ck" for="{name}-{n}">'
                f'<input type="checkbox" id="{name}-{n}" checked data-pp="{item.pp:.4f}" data-tipo="{item.tipo}">'
                f'<span class="ck-body"><span class="ck-title">{esc(item.title)}</span>'
                f'<span class="ck-tags"><span class="code">{esc(item.code)}</span>'
                f'<span class="tipo t-{item.tipo}">{TIPO_LABEL[item.tipo]}</span>'
                f'<span class="ck-pts">{pts} pontos</span></span>{extra}</span>'
                f'<span class="ck-pp">+{pp_text(item.pp)}<small> p.p.</small></span>'
                "</label></li>"
            )
        return f'<ul class="checklist">{"".join(out)}</ul>'

    def diag_mock(self) -> str:
        return self.checklist(MESA, "diag", show_count=False)

    def suzano_perdas(self) -> str:
        return self.checklist(SUZANO_PERDAS, "suz", show_count=False)

    def suzano_historico(self) -> str:
        hist = self.ds.history(EXEMPLO)
        cells = "".join(
            f'<li class="strip-cell f-{FAIXA_CLASS[f]}{" is-now" if ano == ANO_FOCO else ""}">'
            f'<span class="strip-year">{ano}</span><span class="strip-fx">{esc(f)}</span></li>'
            for ano, f in hist.items()
        )
        return f'<ol class="strip" aria-label="Faixa do IEG-M de Suzano por ano-base, 2014 a 2024">{cells}</ol>'

    def suzano_indices(self) -> str:
        bands = self.ds.bands_by_index(EXEMPLO, ANO_FOCO)
        names = {i.code: i.name for i in INDICES}
        items = "".join(
            f'<li><span class="idx-code">{esc(code)}</span><span class="idx-name">{esc(names[code])}</span>{self.chip(f)}</li>'
            for code, f in bands.items()
        )
        return f'<ul class="idx-list" aria-label="Faixas de Suzano por índice, ano-base 2024">{items}</ul>'

    def alto_tiete(self) -> str:
        head = "".join(f'<th scope="col" title="{esc(i.name)}">{esc(i.code)}</th>' for i in INDICES)
        rows = []
        for nome in VIZINHOS:
            rec = self.ds.municipio(nome, ANO_FOCO)
            is_ex = nome == EXEMPLO
            cells = "".join(f'<td class="hm f-{FAIXA_CLASS[rec[i.key]]}">{esc(rec[i.key])}</td>' for i in INDICES)
            mark = ' <span class="ex-tag">exemplo</span>' if is_ex else ""
            row_cls = ' class="is-ex"' if is_ex else ""
            rows.append(
                f'<tr{row_cls}><th scope="row">{esc(nome)}{mark}</th>'
                f'<td class="hm hm-geral f-{FAIXA_CLASS[rec["iegm"]]}">{esc(rec["iegm"])}</td>{cells}</tr>'
            )
        return (
            '<div class="table-scroll"><table class="tbl heat">'
            '<caption class="sr">Faixas oficiais do ano-base 2024, em ordem alfabética</caption>'
            f'<thead><tr><th scope="col">Município</th><th scope="col">IEG-M</th>{head}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )


class Diagrams:
    """Architecture diagram, drawn once and emitted inline (themed by the page) and as files."""

    STANDALONE_STYLE = """
.dg-bg{fill:#f3f6f5}.dg-frame{fill:none;stroke:#a9b8b8;stroke-width:1}
.dg-box{fill:#ffffff;stroke:#a9b8b8;stroke-width:1}.dg-core{fill:#00616a;stroke:none}
.dg-own{fill:#fff6d6;stroke:#d9ad1f;stroke-width:1}
.dg-t{fill:#0f2228;font:600 14px 'Atkinson Hyperlegible Next',system-ui,sans-serif}
.dg-s{fill:#3f5258;font:400 12.5px 'Atkinson Hyperlegible Next',system-ui,sans-serif}
.dg-h{fill:#3f5258;font:600 11.5px 'IBM Plex Mono',ui-monospace,monospace;letter-spacing:.06em}
.dg-core-t{fill:#ffffff;font:700 15px 'Atkinson Hyperlegible Next',system-ui,sans-serif}
.dg-core-s{fill:#d8eef0;font:400 12.5px 'Atkinson Hyperlegible Next',system-ui,sans-serif}
.dg-arrow{fill:none;stroke:#3f5258;stroke-width:1.5}.dg-arrow-own{fill:none;stroke:#b8901a;stroke-width:1.5}
.dg-head{fill:#3f5258}.dg-head-own{fill:#b8901a}
@media (prefers-color-scheme:dark){
.dg-bg{fill:#0e1517}.dg-frame{stroke:#3b4d51}.dg-box{fill:#152024;stroke:#3b4d51}
.dg-core{fill:#73c3cc}.dg-own{fill:#2a2512;stroke:#b8901a}
.dg-t{fill:#e6eeef}.dg-s,.dg-h{fill:#b2c1c4}.dg-core-t{fill:#0b1214}.dg-core-s{fill:#123a40}
.dg-arrow{stroke:#b2c1c4}.dg-head{fill:#b2c1c4}.dg-arrow-own{stroke:#e3b831}.dg-head-own{fill:#e3b831}}
"""

    @staticmethod
    def _text(x: float, y: float, lines: list[str], cls: str, anchor: str = "start", lh: float = 17) -> str:
        spans = "".join(
            f'<tspan x="{x}" dy="{0 if n == 0 else lh}">{esc(line)}</tspan>' for n, line in enumerate(lines)
        )
        return f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{spans}</text>'

    def _box(self, x: float, y: float, w: float, h: float, title: str, sub: list[str], kind: str = "box") -> str:
        cls_box = {"box": "dg-box", "core": "dg-core", "own": "dg-own"}[kind]
        cls_t = "dg-core-t" if kind == "core" else "dg-t"
        cls_s = "dg-core-s" if kind == "core" else "dg-s"
        out = f'<rect class="{cls_box}" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>'
        out += self._text(x + 12, y + 22, [title], cls_t)
        if sub:
            out += self._text(x + 12, y + 41, sub, cls_s, lh=16)
        return out

    @staticmethod
    def _arrow(points: list[tuple[float, float]], own: bool = False) -> str:
        path = "M" + " L".join(f"{px},{py}" for px, py in points)
        (x1, y1), (x2, y2) = points[-2], points[-1]
        cls = "dg-arrow-own" if own else "dg-arrow"
        head_cls = "dg-head-own" if own else "dg-head"
        if abs(x2 - x1) >= abs(y2 - y1):
            d = 1 if x2 > x1 else -1
            head = f"M{x2},{y2} L{x2 - 8 * d},{y2 - 4.5} L{x2 - 8 * d},{y2 + 4.5} Z"
        else:
            d = 1 if y2 > y1 else -1
            head = f"M{x2},{y2} L{x2 - 4.5},{y2 - 8 * d} L{x2 + 4.5},{y2 - 8 * d} Z"
        return f'<path class="{cls}" d="{path}"/><path class="{head_cls}" d="{head}"/>'

    @staticmethod
    def _line(points: list[tuple[float, float]], own: bool = False) -> str:
        path = "M" + " L".join(f"{px},{py}" for px, py in points)
        return f'<path class="{"dg-arrow-own" if own else "dg-arrow"}" d="{path}"/>'

    def horizontal(self) -> tuple[str, str]:
        w, h = 1040, 400
        p: list[str] = []
        p.append(self._text(16, 24, ["DADOS DO PRÓPRIO MUNICÍPIO"], "dg-h"))
        p.append(self._box(16, 36, 210, 56, "AUDESP e balancetes", ["entregas do próprio município"], "own"))
        p.append(
            self._text(
                372,
                48,
                [
                    "Preenchimento prévio de itens calculados:",
                    "i-Fiscal, 850 de 1000 pontos;",
                    "i-Plan, 650 de 1000 pontos.",
                ],
                "dg-s",
                lh=17,
            )
        )
        p.append(self._text(16, 124, ["FONTES PÚBLICAS DO TCESP"], "dg-h"))
        sources = [
            ("Matriz oficial", ["planilha de instrução"]),
            ("Manual da edição", ["fórmulas e regras"]),
            ("CSV de respostas", ["painel, por ano-base"]),
            ("Faixas oficiais", ["painel, 644 municípios"]),
        ]
        sy = [136, 200, 264, 328]
        for (title, sub), y in zip(sources, sy):
            p.append(self._box(16, y, 210, 52, title, sub))
        p.append(self._box(276, 150, 150, 130, "Ingestão", ["versionada", "por edição", "do índice"]))
        p.append(
            self._box(
                476,
                150,
                180,
                130,
                "Motor de cálculo",
                ["sete índices,", "rebaixamentos", "e faixa geral;", "regras abertas"],
                "core",
            )
        )
        p.append(self._box(476, 326, 180, 56, "Validação", ["644 municípios, 11 anos"]))
        p.append(
            self._box(
                706,
                150,
                160,
                130,
                "Diagnóstico",
                ["pontos na mesa:", "norma, processo", "ou investimento;", "simulação e se"],
            )
        )
        p.append(self._box(906, 100, 124, 92, "Relatório", ["prefeito e", "secretarias"]))
        p.append(self._box(906, 240, 124, 92, "Evidências", ["documento por", "resposta Sim"]))
        for y in sy[:3]:
            p.append(self._line([(226, y + 26), (251, y + 26)]))
        p.append(self._line([(251, 162), (251, 290)]))
        p.append(self._arrow([(251, 215), (276, 215)]))
        p.append(self._arrow([(226, 64), (351, 64), (351, 150)], own=True))
        p.append(self._arrow([(426, 215), (476, 215)]))
        p.append(self._arrow([(226, 354), (476, 354)]))
        p.append(self._arrow([(566, 326), (566, 280)]))
        p.append(self._arrow([(656, 215), (706, 215)]))
        p.append(self._arrow([(866, 195), (886, 195), (886, 146), (906, 146)]))
        p.append(self._arrow([(866, 235), (886, 235), (886, 286), (906, 286)]))
        return f"0 0 {w} {h}", "".join(p)

    def vertical(self) -> tuple[str, str]:
        w, h = 360, 920
        p: list[str] = []
        p.append(self._text(16, 20, ["FONTES PÚBLICAS DO TCESP"], "dg-h"))
        sources = [
            ("Matriz oficial", ["planilha de instrução"]),
            ("Manual da edição", ["fórmulas e regras"]),
            ("CSV de respostas", ["painel, por ano-base"]),
            ("Faixas oficiais", ["painel, 644 municípios"]),
        ]
        sy = [30, 88, 146, 204]
        for (title, sub), y in zip(sources, sy):
            p.append(self._box(16, y, 328, 50, title, sub))
        p.append(self._text(16, 284, ["DADOS DO PRÓPRIO MUNICÍPIO"], "dg-h"))
        p.append(
            self._box(
                16,
                294,
                328,
                72,
                "AUDESP e balancetes",
                ["preenchimento prévio de itens calculados:", "i-Fiscal 850 e i-Plan 650 de 1000 pontos"],
                "own",
            )
        )
        p.append(self._box(16, 402, 328, 56, "Ingestão", ["versionada por edição do índice"]))
        p.append(
            self._box(
                16,
                494,
                328,
                92,
                "Motor de cálculo",
                ["sete índices, rebaixamentos e faixa geral", "regras abertas"],
                "core",
            )
        )
        p.append(self._box(16, 622, 328, 56, "Validação", ["contra 644 municípios em 11 anos-base"]))
        p.append(
            self._box(
                16, 714, 328, 76, "Diagnóstico", ["pontos na mesa: norma, processo ou", "investimento; simulação e se"]
            )
        )
        p.append(self._box(16, 826, 160, 76, "Relatório", ["prefeito e", "secretarias"]))
        p.append(self._box(184, 826, 160, 76, "Evidências", ["documento por", "resposta Sim"]))
        for y in sy[1:3]:
            p.append(self._line([(16, y + 25), (6, y + 25)]))
        p.append(self._arrow([(16, 55), (6, 55), (6, 430), (16, 430)]))
        p.append(self._arrow([(180, 366), (180, 402)], own=True))
        p.append(self._arrow([(180, 458), (180, 494)]))
        p.append(self._arrow([(180, 622), (180, 586)]))
        p.append(self._arrow([(344, 229), (354, 229), (354, 650), (344, 650)]))
        p.append(self._arrow([(16, 560), (6, 560), (6, 752), (16, 752)]))
        p.append(self._arrow([(96, 790), (96, 826)]))
        p.append(self._arrow([(264, 790), (264, 826)]))
        return f"0 0 {w} {h}", "".join(p)

    @staticmethod
    def svg(view: str, body: str, label: str, standalone: bool, cls: str) -> str:
        title = "<title>Arquitetura da proposta</title>"
        desc = f"<desc>{esc(label)}</desc>"
        if standalone:
            w, h = view.split()[2:]
            return (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" width="{w}" height="{h}" role="img">'
                f"{title}{desc}<style>{Diagrams.STANDALONE_STYLE}</style>"
                f'<rect class="dg-bg" x="0" y="0" width="{w}" height="{h}"/>{body}</svg>\n'
            )
        return (
            f'<svg class="diagram {cls}" viewBox="{view}" role="img" aria-labelledby="{cls}-t {cls}-d" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{cls}-t">Arquitetura da proposta</title><desc id="{cls}-d">{esc(label)}</desc>{body}</svg>'
        )


ARQ_LABEL = (
    "Fontes públicas do TCESP (matriz oficial, manual da edição, CSV de respostas e faixas oficiais) "
    "e dados do próprio município (AUDESP e balancetes) entram na ingestão, versionada por edição. "
    "A ingestão alimenta o motor de cálculo, validado contra as faixas oficiais de 644 municípios em 11 anos-base. "
    "O motor alimenta o diagnóstico, que gera o relatório e a lista de evidências. "
    "O AUDESP permite preenchimento prévio dos itens calculados: 850 de 1000 pontos no i-Fiscal e 650 de 1000 no i-Plan."
)


class Builder:
    def __init__(self) -> None:
        self.ds = Dataset(DATA / "faixas_all.json", DATA / "media_estadual_por_indice_2014_2024.json")
        self.render = Renderer(self.ds)
        self.diagrams = Diagrams()

    def derived_json(self) -> dict[str, dict]:
        ds = self.ds
        base = {
            "fonte": "Painel do IEG-M do TCESP, faixas oficiais e média estadual por índice",
            "observacao": "Arquivos derivados de data/faixas_all.json e data/media_estadual_por_indice_2014_2024.json",
        }
        retrato = {
            **base,
            "municipios": TOTAL_MUNICIPIOS,
            "faixas_iegm_por_ano_base": ds.distribution_by_year(),
            "faixas_por_indice_2024": {i.code: ds.distribution(ANO_FOCO, i.key) for i in INDICES},
            "municipios_em_c_por_indice_2024": ds.c_by_index(ANO_FOCO),
            "transicoes_2023_para_2024": ds.transitions("2023", "2024"),
        }
        media = {
            **base,
            "escala": "0 a 1; média dos 644 municípios publicada pelo painel",
            "pesos": {i.code: i.weight for i in INDICES},
            "media_por_indice": {a: {i.code: round(ds.media[a][i.key], 4) for i in INDICES} for a in ds.anos},
            "media_ponderada_iegm": {a: round(ds.weighted_mean(a), 4) for a in ds.anos},
        }
        exemplo = {
            **base,
            "municipio": EXEMPLO,
            "codigo_ibge": ds.municipio(EXEMPLO, ANO_FOCO)["codigo_municipio"],
            "historico_iegm": ds.history(EXEMPLO),
            "faixas_por_indice_2024": ds.bands_by_index(EXEMPLO, ANO_FOCO),
            "vizinhos_alto_tiete_2024": {
                n: {"iegm": ds.municipio(n, ANO_FOCO)["iegm"], **ds.bands_by_index(n, ANO_FOCO)} for n in VIZINHOS
            },
        }
        return {"retrato_estado.json": retrato, "media_estadual.json": media, "exemplo_suzano.json": exemplo}

    def fragments(self) -> dict[str, str]:
        hv, hb = self.diagrams.horizontal()
        vv, vb = self.diagrams.vertical()
        arq = Diagrams.svg(hv, hb, ARQ_LABEL, False, "dg-h-wide") + Diagrams.svg(
            vv, vb, ARQ_LABEL, False, "dg-v-narrow"
        )
        return {
            "faixas-por-ano": self.render.faixas_por_ano(),
            "c-por-indice": self.render.c_por_indice(),
            "medias": self.render.medias(),
            "mesa": self.render.mesa(),
            "diag-mock": self.render.diag_mock(),
            "suzano-historico": self.render.suzano_historico(),
            "suzano-indices": self.render.suzano_indices(),
            "suzano-perdas": self.render.suzano_perdas(),
            "alto-tiete": self.render.alto_tiete(),
            "arquitetura": arq,
        }

    @staticmethod
    def inject(page: str, fragments: dict[str, str]) -> str:
        for name, content in fragments.items():
            pattern = re.compile(rf"(<!-- gerado:{re.escape(name)} -->)(.*?)(<!-- /gerado:{re.escape(name)} -->)", re.S)
            if not pattern.search(page):
                raise LookupError(f"marker {name!r} not found in index.html")
            page = pattern.sub(lambda m: m.group(1) + content + m.group(3), page)
        return page

    def run(self, check_only: bool) -> None:
        Verifier(self.ds).run()
        if check_only:
            LOG.info("check finished, nothing written")
            return
        for name, payload in self.derived_json().items():
            (DATA / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            LOG.info("wrote data/%s", name)
        IMG.mkdir(parents=True, exist_ok=True)
        hv, hb = self.diagrams.horizontal()
        vv, vb = self.diagrams.vertical()
        (IMG / "arquitetura-horizontal.svg").write_text(Diagrams.svg(hv, hb, ARQ_LABEL, True, ""), encoding="utf-8")
        (IMG / "arquitetura-vertical.svg").write_text(Diagrams.svg(vv, vb, ARQ_LABEL, True, ""), encoding="utf-8")
        LOG.info("wrote assets/img/arquitetura-*.svg")
        page = INDEX.read_text(encoding="utf-8")
        INDEX.write_text(self.inject(page, self.fragments()), encoding="utf-8")
        LOG.info("updated index.html")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only verify the numbers")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    Builder().run(check_only=args.check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
