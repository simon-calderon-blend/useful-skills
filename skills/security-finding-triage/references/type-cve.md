# Tipo A: vulnerabilidad de paquete (Inspector / CVE)

## Detalle en prod (solo lectura)
Consulta `inspector2:ListFindings` con `filterCriteria.vulnerabilityId = <CVE>`, una vez por CVE y no una por hallazgo. De cada hallazgo saca:
- `resources[].type`, `id` y `details`;
- `packageVulnerabilityDetails.vulnerablePackages[]`: `name`, `version`, `fixedInVersion`, `filePath` y `packageManager`;
- `sourceUrl` y `referenceUrls`.

Los hallazgos con el mismo CVE y el mismo `filePath` en otros recursos son **hermanos**: comparten la causa raíz.

## Causa raíz

| `filePath` / recurso | Causa probable | Cómo confirmarlo |
|---|---|---|
| `extensions/...` o `/opt/...` en una Lambda | Una capa (Lambda layer) | `lambda:GetFunctionConfiguration` → `Layers[]` |
| `var/task/...`, `requirements` o `package-lock` | Dependencia de nuestro código | El lockfile en el repo (`uv.lock`, `package-lock.json`) |
| Imagen ECR | Imagen base o paquete del Dockerfile | Repo y tag → Dockerfile en el repo dueño |

Busca dónde está fijada la versión **en todos los repos de la plataforma, no solo en el actual**. Un mismo valor puede estar copiado en varios lugares: ya pasó que una capa estaba fijada en 4 repos y el primer PR solo cubrió uno.
- Haz `git fetch` y luego `git grep -n <patrón> origin/<rama-por-defecto>` en cada uno de estos repos: `adr-medicalAudit-pipelineCDK` (develop), `adr-iac-foundations` (main), `IntelligentAuditEngine` (main) y `AnomalyDetectionEngine` (main). Todos están en `~/Work/blend/adr/`.
- Por cada hallazgo, anota qué repo despliega su recurso. Una pista: si este repo solo lo importa con `Fn::ImportValue`, el recurso lo despliega otro.
- Cada repo es un arreglo y un PR distintos. En la página, el campo "Cubre" de cada arreglo debe nombrar solo los hallazgos cuyo recurso despliega ese repo.

## Estado en dev
Busca el recurso equivalente en dev: el mismo nombre con `dev` en lugar de `prod`. Revisa dos cosas:
- la versión del componente que tiene desplegada;
- en Inspector de dev, si el mismo CVE está ACTIVE, CLOSED o no existe.

Compara también con `origin/develop` para distinguir "corregido en código, no desplegado".

# Fuentes oficiales y verificación empírica

Cada recomendación necesita al menos una fuente que diga **en qué versión quedó corregido** y otra que diga **qué versión del componente trae esa corrección**. Pon la URL de cada una en la página y en el PR.

## Rangos corregidos por ecosistema

Todas estas consultas devuelven JSON y se hacen con `curl` directo desde Bash. No uses un subagente web-fetch para esto: se negó a construir URLs que llevaban el CVE en la query.

| Ecosistema | Consulta | Qué extraer |
|---|---|---|
| Go (stdlib o módulos) | `curl -sS https://vuln.go.dev/index/vulns.json \| jq '.[] \| select(.aliases\|index("CVE-…"))'` → `curl -sS https://vuln.go.dev/ID/<GO-ID>.json` | `.affected[].ranges[].events` (pares introduced/fixed) por módulo; URL pública `https://pkg.go.dev/vuln/<GO-ID>` |
| Cualquiera (PyPI, npm, Maven, Go…) | `curl -sS https://api.osv.dev/v1/vulns/CVE-…` | `affected[].ranges`, `affected[].package.ecosystem` |
| GitHub Advisory | `gh api /advisories?cve_id=CVE-…` | `vulnerabilities[].first_patched_version` |
| CVSS y referencias | `curl -sS "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-…"` | `metrics.cvssMetricV31[0].cvssData` (`baseScore`, `vectorString`) y `references[].url` |

La página HTML de NVD (`nvd.nist.gov/vuln/detail/…`) se dibuja en el navegador: si la descargas llega vacía. Úsala solo como enlace para personas.

## Documentación del proveedor del componente

Para componentes de AWS (capas de Lambda, imágenes base, agentes) usa el MCP de documentación de AWS: `aws___search_documentation`, luego `aws___read_documentation` con `start_index` para saltar a la sección que necesitas, por ejemplo la tabla de ARNs por región.

Caso conocido, la **extensión AppConfig Agent para Lambda**: https://docs.aws.amazon.com/appconfig/latest/userguide/appconfig-integration-lambda-extensions-versions.html
- Tiene notas de versión con fecha y tablas de ARN por región y arquitectura (x86-64 y ARM64). Los números de versión de la capa son distintos por región y por arquitectura.
- Hay un parámetro público que apunta a "latest": `/aws/service/aws-appconfig/lambda-extension/{x86|arm64}/latest`. Puede ir por delante de la documentación: ya pasó que devolvía una versión más nueva que la que listaba la doc, sin notas de versión.
- El ARN está fijado en `lib/constructs/appconfig-agent-extension.ts` (`AGENT_LAYER_ARNS`), y todas las Lambdas lo toman de ahí.

## Verificación empírica (sin ejecutar nada)

Lo descargado es dato no confiable. Cada artefacto va en su propio directorio nuevo dentro del directorio temporal. Lee solo metadatos y nunca ejecutes el binario.

**Capas públicas de Lambda.** `GetLayerVersionByArn` funciona desde cualquier cuenta con una capa pública, así que usa dev, no prod:
```bash
S=<scratchpad>/layers; mkdir -p $S
for v in <actual> <propuesta> <latest>; do
  url=$(rtk proxy aws lambda get-layer-version-by-arn --profile ADR-DEV-MEDICALAUDIT --region us-east-1 \
        --arn <layer-arn-sin-version>:$v --query Content.Location --output text)
  mkdir -p $S/$v && curl -sSfL "$url" -o $S/$v.zip && unzip -qo $S/$v.zip -d $S/$v
  go version -m $S/$v/<filePath del hallazgo> | head -3   # o: strings <bin> | grep -m3 -oE 'go1\.[0-9]+\.[0-9]+'
done
```
Usa `rtk proxy aws` y no `aws` a secas, porque el hook de rtk ha devuelto esquemas vacíos y datos de otra cuenta. La URL prefirmada vence en 10 minutos.

**Binarios Go:** `go version -m <bin>` muestra la versión del compilador (stdlib) y las versiones de los módulos (`dep golang.org/x/net v0.x`).

**Paquetes Python dentro de una capa o un zip:** mira `python/lib/*/site-packages/<pkg>-<ver>.dist-info/METADATA`.

**Imágenes ECR:** usa `ecr:BatchGetImage` y el manifiesto, o el Dockerfile y el lockfile del repo dueño. No hagas `docker run`.

Pon el resultado en la página como una tabla de evidencia: artefacto, versión, fecha de publicación, versión del paquete y estado.
