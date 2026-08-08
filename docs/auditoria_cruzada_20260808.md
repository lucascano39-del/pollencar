# Auditoría cruzada — sesión "modelo MRP" → sesión "serie poll-of-polls"

**Fecha**: 2026-08-08 · **Caso**: pereira-enc2026 · **Insumos**: handoff 2026-08-08 + 5 archivos
(driver `aggregate_polls.py`, crudo AG feb, comentarios AG ago, microdata widget ago,
participación por edad Encarnación 2001-2023). Todo lo afirmado acá fue **recontado en esta
sesión** desde los crudos; lo no re-contable se marca como GAP.

---

## 1 · Recuentos independientes (todos cierran)

| Ítem | Ellos | Yo (recuento) | Veredicto |
|---|---|---|---|
| Microdata widget ago vs captura de Lucas | 1.735 P / 1.930 C (3.665) | idéntico 1:1, salvo **1 fila**: su parser excluyó el voto del perfil del propio candidato ("Carlos Pereira Rieve") que la captura sí lista | ✔ fiel; diferencia explicada |
| Comentarios ago persona-nivel | 227 P / 358 C (61,2% C) | primer-voto-por-perfil: 228 P / 361 C; excluyendo los 3 perfiles con votos contradictorios: **227 P / 359 C (61,3% C)** — coincide con su 227 | ✔ confirma bajo cualquier regla de dedup |
| Reacciones feb | 902 P / 1.662 C (35,2% P) | aritmética del crudo cierra (2.564 mapeadas) | ✔ |
| Calibrado puntual de mi obs con h clase | 57,0 P | logit(0,451)+0,479 → 57,0 | ✔ reproducido |

## 2 · Canal comentarios: nueva evidencia (linkage al padrón por bando)

Enlace Fellegi-Sunter de los 589 comentaristas-votantes contra el padrón (89.097):

| Bando | n | auto-link | sin enlace | masa en-marco | afiliación de los auto-link |
|---|---|---|---|---|---|
| Cheba | 361 | 22,4% | 13,6% | **0,72** | ANR 68/81 (84%) |
| Pereira | 228 | 11,8% | 18,0% | 0,65 | PLRA 12, ANR-PLRA 8, ANR 4, resto 3 |

- El 61% de Cheba en comentarios **no es fabricación**: sus comentaristas son MÁS verificables
  como electores reales de Encarnación que los de Pereira, y masivamente ANR. Esto **respalda
  el retiro del VEREDICTO #1** de la otra sesión (la card reportaba el widget; la divergencia
  61/53 entre canales es autoselección real por canal).
- **Cluster guionado pro-Cheba, real pero chico**: 20 comentarios con formato consigna
  ("Por/Con/Vamos/Apoyo…"; 20 C vs 2 P). Su masa en-marco media 0,57 vs 0,73 del resto;
  5 con masa 0,00 (sin candidato en padrón: "Wilson Osorio", "Saul Delballe", "Alfredo
  Montiel", "Ernesto Valenzuela", "Emilio Flores") → probables cuentas falsas. Quitarlos
  mueve el canal de 61,3% → 59,9% C. **No cambia conclusiones.**
- Astroturf hay de los dos lados y por canales distintos: consignas pro-Cheba en comentarios;
  páginas político-institucionales votando pro-Pereira en el widget (13 vs 3).

## 3 · Adjudicación §3 — integración de mi obs en su agregado: **SOBRE-CORRECCIÓN CONFIRMADA**

Aplicar h de clase (−0,479 logit ≈ −23,5pp@50, estimado sobre obs **crudas** de la clase
núcleo) a mi observación **ya corregida por marco y composición** cuenta dos veces la parte
composicional del sesgo de casa. La clase núcleo mezcla: (composición ANR de la audiencia +
fuera-de-distrito + selección dentro de celda). Mi MRP ya removió las dos primeras
(verificable: crudo 52,6 C → en-marco 55,6 C → MRP 54,9 C). Lo único que mi IC declara no
cubrir es la **selección dentro de celda**, cuyo tipping es ±0,20 logit (participación
diferencial 1,22×) — 2,4 veces menor que el h aplicado (0,479/0,197).

**Reconstrucción** (gaussiano conjunto, priors de ellos, n_eff escala DDC≈42, y_i recontados):

| Escenario | μ Pereira (con θ₀) | solo-datos |
|---|---|---|
| S0 — tratamiento de ellos (mi obs comparte h núcleo) | 48,8 | 46,5 |
| S1 — mi obs con h propio N(−0,10, 0,20) *(recomendado)* | 47,6 | 45,2 |
| S2 — mi obs con h propio N(0, 0,25) | 47,2 | 44,6 |
| S3 — sin mi obs | 47,6 | 44,4 |

En ningún escenario coherente μ llega a 50,9 P. Su 50,9 es alcanzable solo con el prior
θ₀=53,4 pesando ~2× lo declarado o con h's mayores a los que el modelo conjunto estima.
Su propio "solo-datos 49,8" ya concede ≤50. **GAP**: no puedo replicar el motor exacto —
el handoff no incluyó `poll_engine.py`, `polls_registry.csv` ni los n_eff por obs de
Paraná/Meridiano (que usan estimadores profundos, no crudos). Pedirlos para cerrar la
divergencia 50,9 vs 48,8 en S0.

**Recomendación**: mi obs debe entrar con clase propia `mrp_calibrada`, prior de h
N(−0,10, 0,20²) en logit-Pereira (residuo esperado chico, leve pro-Cheba por la evidencia
del canal comentarios), y n_eff por DDC del **residuo** (no del crudo): el aplastamiento a
42 es defendible como conservador, la corrección puntual de −23,5pp no.

## 4 · Adjudicación §4 — desacuerdos abiertos

1. **Residuo de autoselección del widget**: ni "~23,5pp" ni "cero". Cota de esta sesión:
   ±5pp (tipping 1,22×), con leve asimetría esperada pro-Cheba en ESTA página. El bracket
   profundo correcto es Paraná-MRP 52,5 P (casa pro-P, nov) ↔ AG-MRP 45,1 P (casa pro-C,
   ago): las dos mejores mediciones difieren 7,4pp con 8 meses y clase de casa opuesta —
   compatible con residuos de casa de ±2-4pp cada una más un drift temporal no identificado.
2. **Marco 89.097 vs 89.174**: mi 89.097 = filas del padrón definitivo TSJE xlsx (asserts en
   pipeline). Δ=77 (0,086%), inmaterial para shares. Reconciliar por confronte de sets de
   cédulas por distrito, no por totales. GAP: no tengo su DAC-DB.
3. **Su call 51/49 P**: NO se sostiene como lectura de los datos. Con la sobre-corrección
   removida, el agregado multi-casa queda 47-49 P (51-53 C) con banda total mucho más ancha
   (su propio IC [42,8-58,9]). El nivel sigue **prior-driven** (sin ancla neutral, como su
   propio motor advierte). Lectura defendible del agregado: **empate técnico genuino con
   leve inclinación a Cheba en agosto**; el 51/49 P descansa en θ₀ (urnas 2015/2021) +
   h sobre-aplicado.

## 5 · Lo que esta sesión incorporó del handoff (mejoras a MI modelo)

- **Curvas de participación por edad de urnas reales** (municipales 2021 primaria; 2015 y
  forma 2023 como sensibilidad; target 56,8%) reemplazan mi curva prior. Config actualizada,
  pipeline re-corrido (`data/reference/encarnacion_age_turnout.csv`; provenance: handoff,
  no verificado contra TSJE por esta sesión — GAP menor). **Resultado recalibrado**:
  MRP votante probable **54,9→55,0 C [52,6–57,4]**, y las tres curvas dan 54,96–55,00 —
  la obs `analytics_0806` para el registry queda: pereira 45,0 / cheba 55,0, n=2760.
  El supuesto de participación es inmaterial para esta obs.
- Confirmación externa de mi captura (microdata 1:1) y del descuento del voto del candidato.

## 6 · Pedidos a la otra sesión para cerrar

1. `poll_engine.py` + `polls_registry.csv` + n_eff por obs (cierra divergencia S0).
2. Los y_i profundos de Meridiano (integrado) y Paraná (MRP) con sus IC.
3. Confronte de cédulas DAC-DB vs padrón xlsx (Δ77).
4. Segunda página con widget en agosto (identifica h de casa vs residuo — el desacuerdo §4.1
   es irresoluble con una sola casa profunda por clase).
