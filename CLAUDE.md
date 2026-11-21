# Sparring

App para preparar entrevistas de trabajo en IT con un entrevistador por voz basado en IA.
Primer idioma: español. Primer usuario: el propio autor (preparando una entrevista de Python/backend).

## Idea central

El usuario aporta la **oferta de trabajo completa** y su **CV**. Toda la entrevista se construye a partir de ambos:
las preguntas salen de lo que pide la oferta y de lo que dice el CV, y la evaluación se hace contra los requisitos de esa oferta.

## Flujo del MVP

1. **Configuración:** el usuario pega el texto de la oferta y sube su CV (PDF o Word).
2. **Análisis previo:** el LLM extrae un perfil estructurado (stack, nivel, responsabilidades, lo que el CV cubre, lagunas entre CV y oferta) y genera un plan de entrevista.
3. **Entrevista por voz** en español: el entrevistador habla, escucha, repregunta y cambia de tema según cómo vaya.
4. **Puntuación en segundo plano:** cada respuesta se puntúa contra una rúbrica derivada de la oferta; esas puntuaciones deciden si repreguntar o avanzar.
5. **Informe final:** notas por criterio, encaje con la oferta (qué requisitos se demostraron y cuáles no), fallos detectados, respuestas modelo y qué reforzar.

Una oferta y un CV por sesión. Varias ofertas/CVs por usuario queda fuera del MVP.

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Next.js en Vercel |
| Backend | FastAPI (Python) |
| Voz | ElevenLabs (agente conversacional, conexión directa navegador-ElevenLabs) |
| Conversación | DeepSeek (preguntas, repreguntas, plan de entrevista, informe) |
| Puntuación/decisiones | Jev (`typesafe-ai/jev`, vía Vercel AI Gateway) |
| Datos | Postgres (Neon o Supabase) |

## Arquitectura

- El audio NO pasa por nuestro backend. El navegador se conecta a ElevenLabs con un token/URL firmado que genera FastAPI.
- ElevenLabs usa DeepSeek como modelo personalizado (endpoint compatible con OpenAI) para la conversación.
- FastAPI se encarga de: análisis de oferta y CV, plan de entrevista, rúbrica, puntuación, informe, persistencia.
- FastAPI va en un contenedor (Railway, Render o Fly.io), no en funciones serverless de Vercel, por las conexiones largas.
- Vercel aloja solo el frontend.

## Estructura del repositorio

Este repositorio es **solo el backend** (FastAPI). El frontend (Next.js) vive en un repositorio aparte.

```
sparring/
  CLAUDE.md
  ROADMAP.md
  pyproject.toml   # dependencias y configuración de herramientas (uv, ruff, mypy, pytest)
  uv.lock          # versiones exactas, se versiona en git
  app/             # código de la aplicación
  tests/           # tests con pytest
```

## Convenciones del backend

- Python 3.12+, FastAPI, Pydantic v2 para todos los modelos de entrada y salida.
- Gestión de dependencias con `uv` (`uv add <paquete>`, `uv add --dev <paquete>`). No hay `requirements.txt`.
- Tests con `pytest`. Todo endpoint nuevo lleva al menos un test.
- Configuración y claves por variables de entorno (`.env` fuera del control de versiones). Nunca claves en el código.
- Las llamadas a LLM van encapsuladas en un módulo propio (`app/llm/`) para poder cambiar de proveedor sin tocar el resto.
- Salidas estructuradas del LLM validadas con Pydantic; si fallan, reintentar una vez y devolver error claro.

## Seguridad y privacidad

- El CV y la oferta son **texto no fiable**: pueden contener instrucciones que intenten manipular al entrevistador. Se pasan siempre al modelo como datos delimitados, nunca como instrucciones del sistema.
- El CV contiene datos personales (RGPD): guardar lo mínimo, informar al usuario y ofrecer borrado al terminar la sesión.
- No registrar en logs el contenido del CV ni transcripciones completas.
- Las claves de ElevenLabs y DeepSeek nunca llegan al navegador; solo el token firmado de sesión.

## Decisiones abiertas

- **Jev desde Python:** el ejemplo oficial usa `experimental_decide` del AI SDK (JavaScript). Comprobar si el AI Gateway lo expone como API HTTP utilizable desde FastAPI. Si no, la puntuación se hace en una ruta de Next.js o con DeepSeek como alternativa. Verificar primero.
- **Lectura de la oferta por URL:** muchos portales (LinkedIn, InfoJobs) la bloquean. En el MVP, solo texto pegado.
- **Calidad en español:** probar DeepSeek y la voz de ElevenLabs con respuestas reales en español antes de fiarse de las puntuaciones.

## Fuera del MVP

Varias ofertas/CVs por usuario, editor de código en vivo, historial y progreso, cuentas de pago, inglés.
