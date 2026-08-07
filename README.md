# pollencar — intención de voto Encarnación 2026

Convierte una straw poll de Facebook (autoseleccionada) en una **estimación
modelada de intención de voto** para la intendencia de Encarnación 2026:
enlace nominal al padrón definitivo TSJE (Fellegi-Sunter con pesos por
frecuencia de apellido y fonética paraguaya), modelo multinivel bayesiano con
afiliación partidaria individual como covariable, y post-estratificación MRP
sobre las ~89 mil personas del marco, con imputación múltiple para los enlaces
dudosos (reglas de Rubin).

## Uso

```bash
pip install -r requirements.txt
# colocar en data/raw/: la captura del poll (txt) y el padrón (xlsx)
# registrar la captura en data/raw/waves.json
make all            # pipeline completo -> data/output/informe_agosto2026.html
make fast           # corrida rápida (M=4, sin sensibilidades) para iterar
make test           # tests sintéticos (sin datos reales)
```

Ola nueva (más votos en el mismo poll): soltar la captura nueva en `data/raw/`,
agregar una línea a `waves.json` con `wave: 2`, y `make all`. El pipeline
detecta qué respondentes son nuevos entre capturas y activa el término de ola.

Ancla opcional: si existe `data/raw/resultados_2023_mesa.csv`
(columnas `local,share_cheba_equiv,participacion`), el modelo la usa como
covariable de calibración por local. Sin el archivo, el slot queda inactivo y
declarado en el informe.

## Capas

1. **Insumos** (`io_poll`, `io_padron`): parser de la captura con asserts,
   filtro de páginas/no-personas (léxico + heurísticas), padrón tipado con
   afiliación agrupada, sexo inferido del nombre de pila (mismo clasificador en
   ambos lados) y tablas de frecuencia de apellidos/nombres.
2. **Enlace** (`linkage`): bloqueo por conjunción fonética, vector de
   comparación discreto (apellido/nombre/tercer acuerdo/sexo/Jaro-Winkler), EM
   para m/u, pesos por frecuencia en el acuerdo exacto, posterior por
   respondente con masa de no-match. Tres zonas; los dudosos van a imputación
   múltiple — **nunca se fuerza un match**.
3. **Estimación** (`model`, `sampler_numpy`): binomial-logit multinivel
   (afiliación, sexo, edad, local; ancla 2023 y efecto de ola como términos
   opcionales), Metropolis-within-Gibbs adaptativo en numpy puro, 4 cadenas,
   diagnósticos R̂/ESS.
4. **Post-estratificación** (`poststrat`): θ ponderado por N de celda ×
   probabilidad de voto; escenarios «todos los inscriptos» y «votante
   probable» (curva etaria prior + tipo de inscripción, documentados).
5. **Reporte** (`report`): HTML autocontenido en español con la cadena
   crudo → enlazado → MRP, IC 95%, embudo, enlace diferencial por candidato,
   señal de coordinación, Rubin/FMI, cobertura y límites de lectura.

## Datos

`data/raw/` está fuera de git (padrón con cédulas y capturas con nombres).
Se commitean el código, los léxicos y los agregados de salida (sin
identificadores individuales).
