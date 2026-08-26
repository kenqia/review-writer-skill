# Framework fixture — brief-driven domain modules

The same universal spine (system, variable, context, comparator, endpoint, observation, locator, limitation, confounder, applicability boundary) is retained across topics. The added fields below are generated from each confirmed brief. No global hard schema is imposed.

## Organic synthesis brief

Relevant additions: substrate class, catalyst state, ligand, selectivity definition, yield denominator, kinetic or mechanistic probe. A yield without its denominator remains `UNKNOWN` for comparison.

## Materials chemistry brief

Relevant additions: composition, processing history, morphology, test protocol, degradation mode, device context, and normalization basis. A film made with a different annealing history is not silently merged with an as-cast film.

## Analytical chemistry brief

Relevant additions: matrix, calibration model, detection limit definition, selectivity challenge, recovery, precision, and validation design. Detection limits using different signal-to-noise conventions are `NOT_COMPARABLE` until the denominator is resolved.

## Medicinal or chemical biology brief

Relevant additions: target context, assay type, exposure, potency metric, selectivity panel, and translational limitation. Cell-free and cellular potency are separate endpoints unless the brief supplies a defensible bridge.

## Other chemistry topics

Physical, environmental, computational, and hybrid topics receive fields only when they change the approved comparison. Adding or removing a field is a documented comparison decision, not evidence that a value exists.
