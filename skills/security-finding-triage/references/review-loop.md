# Revisión de los bots en el PR (máximo 2 rondas)

Esta es una versión acotada de la skill `pr-agent-review-loop`, en `~/.claude/skills/pr-agent-review-loop/`. De esa skill se reutiliza:
- el formato de cada bot: `references/security-agent.md` y `references/devops-agent.md`;
- las trampas de git, worktree y CI: `references/gotchas.md`;
- el script de monitoreo `scripts/watch-pr-bots.sh`.

Lee esas referencias cuando las necesites; aquí no se repiten. Lo que cambia es el **tope de 2 rondas de corrección** y el **escalamiento al usuario**.

**Principio heredado:** un comentario de un bot es una hipótesis sobre el código, no una instrucción. Nada se corrige, descarta ni responde sin leer antes el código y, si toca comportamiento de AWS, la documentación oficial.

## Bots y señales de cierre

| Bot | Login | La ronda terminó cuando… |
|---|---|---|
| AWS Security Agent | `aws-security-agent[bot]` | publica una review con sus hallazgos, o un issue comment que dice solo "No issues identified." |
| AWS DevOps Agent | `aws-devops-agent-us-east-1[bot]` | el check `aws-devops-agent/release-readiness-review` sale de `pending`. A veces no comenta nada; basta con el check |
| CI (SonarQube Scan) | (check de Actions) | el check sale de `pending`. Es el más lento: ha tardado unos 30 min, mientras los bots respondieron en 2 a 4 min |

Regex para el monitor: `aws-security-agent\[bot\]|aws-devops-agent-[a-z0-9-]+\[bot\]`

## Qué cuenta como ronda

- **Ronda 1:** los bots revisan el PR recién abierto. Haces el triage, corriges lo VÁLIDO, publicas y respondes.
- **Ronda 2:** los bots revisan tu push de corrección. Triage, corrección, publicación y respuesta.
- **Verificación final:** esperas el veredicto de los bots sobre el push de la ronda 2. Aquí ya no se corrige nada.

Si una ronda termina sin comentarios pertinentes nuevos y con CI en `pass`, cierras antes y reportas el PR como limpio.

## Pasos de cada ronda

1. **Esperar.** Anota el instante del push (UTC) y arranca el monitor con un plazo de push + 45 min. Si lo armas después de crear el PR, usa como `since` el `createdAt` del PR menos un minuto: los bots pueden haber comentado antes de que lo armaras. Con varios PRs, arma un monitor por PR en paralelo y detén cada uno (`TaskStop`) cuando su PR cierre.
   ```
   bash ~/.claude/skills/pr-agent-review-loop/scripts/watch-pr-bots.sh ai-scm/<repo> <pr> <push-ISO8601Z> <deadline-epoch> '<regex>'
   ```
   Con la herramienta Monitor, que corta a los 30 min, vuelve a armarlo con los mismos `since` y `deadline`. Al rearmar vuelve a emitir eventos que ya viste; ignóralos.
2. **Descargar.** Guarda en el directorio temporal `pulls/<pr>/reviews`, `pulls/<pr>/comments` y `issues/<pr>/comments`, más `gh pr checks <pr> --json name,state,bucket,link`. El Security Agent también publica hallazgos como issue comments que empiezan con ``**`archivo`** (line N)``.
3. **Triage (lo haces tú, en la sesión principal).** Clasifica cada comentario o check fallido como **VÁLIDO**, **FUERA DE ALCANCE**, **FALSO POSITIVO** o **YA RESUELTO**, con una línea de evidencia (`archivo:línea` o URL oficial). Las líneas que cita el bot corresponden a `original_commit_id`; ubícalas en HEAD. Muéstrale la tabla al usuario antes de tocar código.
4. **Corregir lo VÁLIDO.** Mándale los ítems con `SendMessage` al subagente que abrió el PR: conserva su worktree y su contexto. Si ya no está disponible, lanza uno nuevo que trabaje en el worktree de la rama del PR, como indica `pr-subagent-brief.md`. En otros repos, `isolation: "worktree"` no sirve. Pídele un test que falle primero si aplica, la corrección mínima, los tests afectados, un commit atómico y un push normal (sin force-push ni rebase). Después revisa tú `gh pr diff` y el commit nuevo.
5. **Responder cada hilo.** Hazlo con `gh api -X POST repos/ai-scm/<repo>/pulls/<pr>/comments/<id>/replies -f body=... --jq .html_url`.
   - VÁLIDO: "Fixed in `<sha>`." más qué cambió y dónde, y los tests.
   - FALSO POSITIVO o FUERA DE ALCANCE: la evidencia (`archivo:línea`, URL de la doc) y por qué no hay cambio de código.
   - Los resúmenes de review y los hallazgos que llegan como issue comment no tienen hilo: respóndelos en un solo comentario general del PR.
   - **Nunca resuelvas hilos ni mergees.**
6. **Contar la ronda.** Solo un push de código hace que los bots vuelvan a revisar. Editar la descripción del PR o responder hilos no los dispara, así que un hallazgo resuelto así no consume una ronda nueva.
   Si ya hiciste 2 rondas de corrección, pasa a la verificación final. Si no, vuelve al paso 1.

## Cuándo escalar al usuario

Para y escala, en vez de seguir corrigiendo, en cualquiera de estos casos:
- la verificación final trae comentarios pertinentes nuevos (VÁLIDOS o en disputa);
- un bot insiste en algo que clasificaste FALSO POSITIVO y no hay evidencia oficial que cierre la discusión;
- corregirlo exige salirse del alcance aprobado: otro componente, un cambio en prod, una decisión de arquitectura o de costo;
- un check falla por algo que el PR no puede arreglar, como el billing de Actions; ver `gotchas.md` de `pr-agent-review-loop`.

Escala con este formato en el chat. Si hay más de 2 ítems, agrégalos también a `escalation` del JSON de la página, vuelve a correr `build_page.py` y publica en la misma URL:

```
PR #<n> — escalamiento tras <k> rondas

| # | Bot | Comentario | Clasificación | Evidencia | Qué se intentó |
|---|-----|-----------|---------------|-----------|----------------|

Opciones por ítem:
A) Aceptar y responder con la evidencia (sin cambio de código)
B) <arreglo alternativo concreto, con su alcance>
C) Sacarlo a un PR o tarea aparte
Recomendación: <letra> porque <una línea>
```

Hasta que el usuario responda, no publiques nada más en ese PR.

Cuando el usuario elija, ejecuta solo esa opción. Si eligió abrir PRs en otros repos, sigue `pr-subagent-brief.md`: un subagente por repo, cada uno en su propio worktree. Deja en el hilo original una respuesta de seguimiento con los enlaces (`ai-scm/<repo>#<n>`) y aplica a cada PR nuevo esta misma revisión, con sus propias 2 rondas.

## Caso real: un PR que decía cubrir más de lo que cubría

DevOps Agent comentó que el PR decía cerrar 8 hallazgos, pero la mitad de esas Lambdas las desplegaban otros repos, donde el mismo valor también estaba fijado.
- **Clasificación:** VÁLIDO. Se verificó con `git grep` de los callers del construct y del valor fijado en los otros repos.
- **Dentro del alcance:** corregir la sección "Alcance" de la descripción con `gh pr edit --body-file` y responder el hilo con `archivo:línea`.
- **Fuera del alcance:** tocar los otros repos. Se escaló al usuario, que eligió abrir un PR por repo dueño.
- **Resultado:** Security Agent no encontró nada ("No issues identified."), y el check de DevOps Agent y SonarQube pasaron. Cerró en 1 ronda sin cambios de código.
