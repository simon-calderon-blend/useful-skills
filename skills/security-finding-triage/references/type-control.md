# Tipo B: control fallido de Security Hub CSPM

Son hallazgos de configuración, no de paquetes. Un recurso no cumple un control como `ECS.5`, `RDS.13`, `EC2.182` o `IAM.28`. Los evalúa AWS Config, y Security Hub los publica en formato ASFF.

## Detalle en prod (solo lectura)
Consulta `securityhub:GetFindings` filtrando por el `Id` del hallazgo. Campos que importan:

| Campo | Para qué sirve |
|---|---|
| `Compliance.SecurityControlId` | El ID del control (`ECS.5`). Es la llave para todo lo demás |
| `Compliance.Status` | `FAILED`, `PASSED`, `WARNING` o `NOT_AVAILABLE` |
| `Compliance.RelatedRequirements` / `GeneratorId` | El estándar que lo pide, por ejemplo CIS v5.0.0 2.2.2 o AWS FSBP |
| `Resources[].Type` / `Id` | El recurso que falla, por ejemplo `AwsEcsTaskDefinition` con su ARN |
| `Remediation.Recommendation.Url` | La documentación oficial de remediación. A veces apunta a la guía del servicio, no a la del control |
| `Workflow.Status` | `NEW`, `NOTIFIED`, `SUPPRESSED` o `RESOLVED` |

**Duplicados:** si la consolidación de hallazgos de control no está activada, el mismo control sale una vez por cada estándar (por ejemplo CIS y FSBP). Deduplica por `SecurityControlId` + `ResourceId`.

**Hermanos:** busca los demás recursos que fallan el mismo control en prod con estos filtros: `ComplianceSecurityControlId = <ID>`, `ComplianceStatus = FAILED` y `RecordState = ACTIVE`.

## Fuente oficial del control
1. Busca la página del control: `aws___search_documentation` con `"[<ID>]"` y el nombre del servicio. Las páginas tienen la forma `https://docs.aws.amazon.com/securityhub/latest/userguide/<servicio>-controls.html`. Saca de ahí:
   - qué parámetro evalúa exactamente y cuándo falla;
   - la regla de AWS Config;
   - el **tipo de programación**: con "Change triggered" se reevalúa al cambiar el recurso; con "Periodic" tarda hasta su periodo;
   - las notas de `NOT_APPLICABLE`.
2. Agrega `Remediation.Recommendation.Url` del hallazgo y la documentación del servicio o del construct de CDK que vayas a cambiar.
3. Opcional, solo lectura: `securityhub:BatchGetSecurityControls` devuelve `RemediationUrl` y los parámetros del control.

## Causa raíz en el IaC
- **Stack dueño:** casi todo lo crea CloudFormation, así que busca la etiqueta `aws:cloudformation:stack-name` del recurso. Puedes leerla con `resourcegroupstaggingapi:GetResources` o con la API de tags del servicio. Del stack llegas al archivo con `git grep` del nombre del stack o del ID lógico en `origin/develop`.
- **Propiedad que falta:** busca en el construct la propiedad que evalúa el control. Ejemplos:
  - `ECS.5`: `readonlyRootFilesystem` en `addContainer`.
  - `RDS.13`: `autoMinorVersionUpgrade` en la instancia o el cluster.
- **Muchos recursos, un construct:** si 20 recursos fallan por el mismo construct o el mismo valor por defecto, es un solo arreglo.
- **Controles de cuenta u organización** (por ejemplo `IAM.28`, Access Analyzer): no viven en este repo. Busca en `adr-iac-foundations`. Si ningún repo es dueño, dilo y propón dónde debería vivir, o propón el cambio manual para que lo haga el usuario.

## Estado en dev
Consulta `securityhub:GetFindings` en dev con `ComplianceSecurityControlId = <ID>` y el `ResourceId` equivalente (`prod` → `dev` en el nombre o en el ARN). Interpreta así:

| Dev | Estado |
|---|---|
| `PASSED` | Corregido en dev; promover |
| `FAILED` | No corregido |
| No hay hallazgo | No evaluable: el estándar puede no estar activo en dev o el recurso no existir. Revisa `securityhub:GetEnabledStandards` y si el recurso existe, y dilo así. No lo cuentes como corregido |

Compara también con `origin/develop`. Si el código ya tiene la propiedad pero dev sigue `FAILED`, el estado es "corregido en código, no desplegado".

## Riesgo en ejecución
Un cambio de configuración puede romper el servicio. Antes de proponerlo, lee el código que corre en el recurso:
- **`ECS.5` (root filesystem de solo lectura):** busca si la app o sus librerías escriben en disco (`/tmp`, caches, archivos de pid, `~/.cache`). Si escriben, el arreglo incluye un volumen escribible montado solo en esas rutas. Pruébalo en dev antes de promover.
- **RDS (versiones menores):** el upgrade ocurre en la ventana de mantenimiento y reinicia la instancia. Anota la ventana actual.
- **IAM y red:** revisa quién usa el permiso o la regla antes de quitarlo.

## Cuando el arreglo es aceptar el riesgo
Aplica si el control no tiene sentido para el recurso o el costo no se justifica. Propón la supresión como un arreglo más en la página, con:
- la justificación técnica y la fuente que la respalda;
- dónde crearla. Primero averigua qué cuenta administra Security Hub: `securityhub:GetAdministratorAccount` en prod (solo lectura). Las automation rules se crean en la cuenta administradora;
- los pasos exactos: una automation rule con criterio `ComplianceSecurityControlId` + `ResourceId` que ponga `Workflow.Status = SUPPRESSED` y una nota. Si existe un repo de IaC dueño de Security Hub, el arreglo va como PR ahí.

**Tú no la ejecutas: es un cambio en una cuenta sensible.**

## Verificación posterior al deploy
Después del deploy en dev, el control debe pasar a `PASSED`. Con "Change triggered" es casi inmediato; con "Periodic", según el periodo de la regla. Escribe esta verificación en el PR, en la sección "Verificación post-deploy".
