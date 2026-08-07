"""Tests sintéticos (sin datos reales): python -m tests.run_all"""

import sys

sys.path.insert(0, "src")

import numpy as np


def test_normalize():
    from pollencar.normalize import canon, split_padron_name, tokens

    assert canon("Käřïňä Äřïyü") == "KARINA ARIYU"
    assert canon("ñandutí") == "ÑANDUTI"
    assert canon("José  María") == "JOSE MARIA"
    assert tokens("Dr. Claudio Díaz de Vivar")[0] == "CLAUDIO"
    sur, giv = split_padron_name("MARTINEZ VDA DE ALVARENGA, MARGARITA")
    assert sur == ["MARTINEZ", "ALVARENGA"] and giv == ["MARGARITA"]
    sur, giv = split_padron_name("ACEVEDO ALTAMIRANO, FRANCO")
    assert sur == ["ACEVEDO", "ALTAMIRANO"] and giv == ["FRANCO"]
    print("normalize ok")


def test_phonetics():
    from pollencar.phonetics import phonetic_key as pk

    pairs = [
        ("VILLALBA", "VIYALVA"), ("CACERES", "KASERES"), ("GIMENEZ", "JIMENEZ"),
        ("BENITEZ", "VENITES"), ("CHAVEZ", "CHABES"), ("ZARATE", "SARATE"),
        ("HECTOR", "ECTOR"), ("YEGROS", "IEGROS"), ("QUINTANA", "KINTANA"),
        ("VAZQUEZ", "VASQUES"), ("OJEDA", "OGEDA"),
        ("SOPHIA", "SOFIA"), ("THIAGO", "TIAGO"),          # PH/TH antes de h muda
        ("SHIRLEY", "CHIRLEY"), ("CHRISTIAN", "CRISTIAN"),  # sh=ch; CH+cons=/k/
    ]
    for a, b in pairs:
        assert pk(a) == pk(b), (a, b, pk(a), pk(b))
    # el dígrafo CH es fonema propio: NO colisiona con C/S/K
    for a, b in [("CHENA", "CENA"), ("CHENA", "SENA"), ("CHANO", "CANO"),
                 ("OCHOA", "OCOA"), ("CHAMORRO", "CAMORRO")]:
        assert pk(a) != pk(b), (a, b, pk(a), pk(b))
    assert "Ñ" in pk("ÑANDUTI")
    print("phonetics ok")


def test_sexo():
    from pollencar.sexo import infer_sex

    assert infer_sex(["MARIA", "JOSE"]) == "F"
    assert infer_sex(["JOSE", "MARIA"]) == "M"
    assert infer_sex(["ROSALINDA"]) == "F"  # fallback -A
    assert infer_sex(["X"]) == "U"
    print("sexo ok")


def test_jaro_winkler():
    from pollencar.linkage import jaro_winkler as jw

    assert jw("MARTHA", "MARHTA") > 0.94
    assert jw("DIXON", "DICKSONX") > 0.75
    assert abs(jw("ABC", "ABC") - 1.0) < 1e-9
    assert jw("ABC", "XYZ") == 0.0
    print("jaro_winkler ok")


def test_parser():
    import os
    import tempfile

    from pollencar.io_poll import parse_capture

    txt = "\n".join(
        ["Candidato Uno", "60% · 6 votos", "Ana Gomez", "Juan Perez",
         "Maria Lopez", "Pedro Diaz", "Rosa Ruiz", "Luis Vera",
         "Candidato Dos", "40% · 4 votos", "Eva Sosa", "Tito Rojas",
         "Nina Baez", "Omar Cano"])
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(txt)
        p = f.name
    cands, df = parse_capture(p)
    os.unlink(p)
    assert len(cands) == 2 and cands[0]["votes_declared"] == 6
    assert len(df) == 10
    print("parser ok")


def test_em_and_zones():
    """EM separa una mezcla sintética clara; m>u en acuerdos."""
    from collections import Counter

    import json

    from pollencar.linkage import em_mu

    cfg = json.load(open("config/config.json"))
    rng = np.random.default_rng(1)
    counts = Counter()
    # no-matches: mayormente desacuerdo
    for _ in range(50000):
        g = (rng.choice(3, p=[0.7, 0.25, 0.05]), rng.choice(4, p=[0.8, 0.1, 0.05, 0.05]),
             rng.choice(3, p=[0.4, 0.1, 0.5]), rng.choice(3, p=[0.4, 0.35, 0.25]),
             rng.choice(4, p=[0.6, 0.25, 0.05, 0.1]))
        counts[g] += 1
    # matches: mayormente acuerdo
    for _ in range(600):
        g = (rng.choice(3, p=[0.02, 0.18, 0.8]), rng.choice(4, p=[0.03, 0.07, 0.2, 0.7]),
             rng.choice(3, p=[0.15, 0.35, 0.5]), rng.choice(3, p=[0.03, 0.72, 0.25]),
             rng.choice(4, p=[0.05, 0.15, 0.7, 0.1]))
        counts[g] += 1
    m, u, p = em_mu(counts, cfg)
    assert m[0][2] > u[0][2], "match debe acordar apellido exacto más que u"
    assert m[1][3] > u[1][3]
    assert 0.001 < p < 0.1
    print(f"em ok (prevalencia {p:.4f})")


def test_sampler_recovery():
    """El sampler recupera un intercepto conocido con cobertura razonable."""
    import json

    from pollencar import model
    from pollencar.model import ModelData
    from pollencar.sampler_numpy import MwG

    import pandas as pd

    cfg = json.load(open("config/config.json"))
    model.make_levels(cfg)
    rng = np.random.default_rng(7)
    true_b0 = 0.4
    rows = []
    for p_ in range(5):
        for s in range(3):
            for a in range(6):
                l = rng.integers(0, 8)
                n = int(rng.integers(10, 60))
                eta = true_b0
                pr = 1 / (1 + np.exp(-eta))
                rows.append({"party_idx": p_, "sex_idx": s, "age_idx": a,
                             "local_idx": int(l), "n": n,
                             "y": int(rng.binomial(n, pr))})
    cells = pd.DataFrame(rows)
    data = ModelData(cells, 8)
    cfg_m = dict(cfg["model"], iters=2500, burnin=1000, chains=1)
    s = MwG(data, cfg_m, 123)
    draws, _ = s.run(cfg_m["iters"], cfg_m["burnin"])
    b0 = np.array([x[0] for x, _ in draws])
    # el intercepto global se reparte con los RE; comparamos la media predicha
    eta_hat = np.array([x[0] + x[3:8].mean() + x[8:14].mean() + x[14:22].mean()
                        for x, _ in draws])
    p_hat = 1 / (1 + np.exp(-eta_hat))
    p_true = 1 / (1 + np.exp(-true_b0))
    lo, hi = np.quantile(p_hat, [0.025, 0.975])
    assert lo - 0.02 < p_true < hi + 0.02, (lo, p_true, hi)
    print(f"sampler ok (p_true={p_true:.3f} en [{lo:.3f},{hi:.3f}])")


def test_rubin():
    from pollencar.rubin import rubin_table

    rng = np.random.default_rng(3)
    draws = [rng.normal(0.52, 0.01, 500) for _ in range(5)]
    t = rubin_table(draws)
    assert 0.5 < t["theta_hat"] < 0.55
    assert t["fmi"] < 0.5
    print("rubin ok")


def test_diagnostics():
    from pollencar.diagnostics import ess_bulk, split_rhat

    rng = np.random.default_rng(4)
    chains = [rng.normal(0, 1, 1000) for _ in range(4)]
    r = split_rhat(chains)
    assert 0.99 < r < 1.02, r
    assert ess_bulk(chains) > 1000
    bad = [rng.normal(0, 1, 1000), rng.normal(3, 1, 1000)]
    assert split_rhat(bad) > 1.5
    print("diagnostics ok")


if __name__ == "__main__":
    test_normalize()
    test_phonetics()
    test_sexo()
    test_jaro_winkler()
    test_parser()
    test_em_and_zones()
    test_sampler_recovery()
    test_rubin()
    test_diagnostics()
    print("\nTODOS LOS TESTS OK")
