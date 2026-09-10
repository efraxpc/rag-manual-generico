# Evaluación LLM-as-a-judge

El evaluador es un proceso offline para desarrollo y CI; no expone un endpoint
público ni participa en una petición de usuario. Los diagramas con tipografía
grande para impresión A4 muestran la ejecución completa:

1. [Tests, configuración y corpus](llm-as-a-judge-a4-01-input.mmd).
2. [Ejecución de la versión candidata](llm-as-a-judge-a4-02-request.mmd).
3. [Evaluación LLM-as-a-judge](llm-as-a-judge-a4-03-gate.mmd).
4. [Reporte, bloqueo y despliegue](llm-as-a-judge-a4-04-report.mmd).

Puntúa cada respuesta de 1 a 5 en:

- `groundedness`: respaldo de las afirmaciones en el contexto recuperado.
- `relevance`: respuesta directa a la pregunta.
- `completeness`: cobertura de la información disponible y de la respuesta esperada.
- `citation_quality`: citas localizables y coherentes con fuente y página.

El modelo genera las puntuaciones y razones, pero el proceso calcula el gate. Un
caso pasa si todas las métricas alcanzan el umbral y no hay afirmaciones materiales
sin respaldo. El reporte identifica los casos, las puntuaciones y las razones, pero
no incluye los campos de pregunta, respuesta o contexto. Las razones siguen siendo
datos derivados del contenido y el reporte debe tratarse como información sensible.

## Flujo completo

El gate no evalúa respuestas estáticas. Primero ejecuta el código RAG de la
versión candidata sobre preguntas versionadas y un corpus controlado:

```text
tests + lint
    → sembrar corpus de evaluación en Azure AI Search
    → recuperar contexto y generar respuestas con el RAG candidato
    → guardar question + answer + context + fuentes
    → ejecutar LLM-as-a-judge
    → desplegar únicamente si el juez devuelve 0
```

La recuperación del baseline actual es textual. No se presenta como vectorial
porque la generación de embeddings todavía no existe en la aplicación.

## Configuración

El juez usa la API v1 de Azure OpenAI con un token de Microsoft Entra ID. La
identidad que ejecuta el comando necesita el rol `Cognitive Services OpenAI User`.
Configura:

```bash
APP_AZURE_OPENAI_ENDPOINT="https://<recurso>.openai.azure.com"
APP_AZURE_OPENAI_CHAT_DEPLOYMENT="<despliegue-generador>"
APP_AZURE_OPENAI_JUDGE_DEPLOYMENT="<despliegue-del-juez>"
```

La generación candidata también requiere un índice exclusivo de evaluación:

```bash
APP_AZURE_SEARCH_ENDPOINT="https://<servicio>.search.windows.net"
APP_AZURE_SEARCH_TEXT_INDEX_NAME="rag-evaluation-chunks"
```

Para ejecución local, `DefaultAzureCredential` puede usar la sesión de Azure CLI.
En Azure usa la identidad administrada; si es asignada por el usuario, configura
`APP_AZURE_MANAGED_IDENTITY_CLIENT_ID`. Conviene que el juez sea un despliegue
distinto y más capaz que el modelo que produjo las respuestas.

El despliegue elegido debe admitir Structured Outputs en Chat Completions. El
endpoint se configura sin el sufijo `/openai/v1`.

## Escenarios y casos generados

El archivo versionado `evaluations/datasets/rag_scenarios.jsonl` contiene solo
la entrada y las expectativas. `document_source` referencia un archivo de
`evaluations/corpus/` que se indexará y se convertirá en un `document_id` estable:

```json
{
  "id": "caso-001",
  "question": "¿Qué indica el manual?",
  "expected_answer": "Respuesta de referencia",
  "expected_sources": ["manual.md"],
  "document_source": "manual.md",
  "top_k": 5
}
```

El comando generador produce el segundo JSONL, que ya contiene la respuesta y
el contexto realmente recuperado por la versión candidata.

## Contrato de casos para el juez

Cada línea del JSONL es un caso independiente:

```json
{
  "id": "caso-001",
  "question": "¿Qué indica el manual?",
  "answer": "La respuesta generada con su cita [manual.pdf, p. 2].",
  "context": [
    {"content": "Fragmento recuperado", "source": "manual.pdf", "page": 2}
  ],
  "expected_answer": "Respuesta de referencia opcional",
  "expected_sources": ["manual.pdf, p. 2"]
}
```

`expected_answer` y `expected_sources` son opcionales. Los demás campos son
obligatorios. Los IDs deben ser únicos. `rag_answers.example.jsonl` se conserva
como ejemplo del contrato intermedio, no como entrada del gate de CI.

## Ejecución y códigos de salida

```bash
python -m app.commands.generate_evaluation_answers \
  evaluations/datasets/rag_scenarios.jsonl \
  --documents-dir evaluations/corpus \
  --output evaluations/results/candidate-answers.jsonl

python -m app.commands.evaluate_answers \
  evaluations/results/candidate-answers.jsonl \
  --output evaluations/results/judge-report.json \
  --threshold 4
```

- `0`: todos los casos pasan el gate.
- `1`: la evaluación terminó, pero uno o más casos no pasan.
- `2`: dataset, configuración, autenticación o proveedor inválidos.

La rúbrica queda versionada como `rag-judge-v1` en el reporte. Para comparar
resultados entre versiones, conserva también el nombre/versionado inmutable del
despliegue del juez y ejecuta siempre el mismo dataset y umbral.

Antes de convertir el resultado en un gate obligatorio, calibra la rúbrica y el
umbral contra una muestra revisada por expertos. Las puntuaciones de un LLM no son
perfectamente deterministas; los casos críticos deben conservar pruebas explícitas y
revisión humana además de este evaluador.

## GitHub Actions y despliegue

`.github/workflows/quality-gate-deploy.yml` ejecuta tests y lint en pull
requests. En `push` a `main` o ejecución manual, usa OIDC para generar y evaluar
respuestas. El job `deploy` declara `needs: rag-quality-gate`, por lo que GitHub
no lo inicia si el generador o el juez devuelve un código distinto de cero.
Las ejecuciones de una misma rama no compiten: un push nuevo cancela el workflow
anterior antes de que pueda promover una versión obsoleta.

Crea los entornos protegidos `evaluation` y `production`. Configura estas
variables de GitHub en el entorno correspondiente:

- Comunes: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`.
- Evaluación: `EVAL_AZURE_SEARCH_ENDPOINT`,
  `EVAL_AZURE_SEARCH_TEXT_INDEX_NAME`, `EVAL_AZURE_OPENAI_ENDPOINT`,
  `EVAL_AZURE_OPENAI_CHAT_DEPLOYMENT` y
  `EVAL_AZURE_OPENAI_JUDGE_DEPLOYMENT`.
- Producción: `AZURE_CONTAINER_REGISTRY_NAME`,
  `AZURE_CONTAINER_IMAGE_REPOSITORY`, `AZURE_CONTAINER_APP_RESOURCE_GROUP` y
  `AZURE_CONTAINER_APP_NAME`.

La identidad federada de evaluación necesita `Search Index Data Contributor`
en el índice exclusivo y `Cognitive Services OpenAI User` en Azure OpenAI. La
identidad de producción necesita permisos para ejecutar ACR Build y actualizar
la Container App. Limita cada identidad a su entorno y recursos respectivos.

El despliegue usa una etiqueta inmutable igual al SHA del commit. Terraform
ignora cambios posteriores en la imagen de la Container App para no revertir la
versión promovida por CI/CD; continúa administrando el resto de la aplicación.
