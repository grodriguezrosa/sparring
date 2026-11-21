# Roadmap de Sparring

## Fase 0: Prototipo para uso propio

Objetivo: poder hacerme una entrevista de Python con voz cuanto antes, aunque sea feo.

- [ ] Repositorio del backend (FastAPI, este) y repositorio aparte del frontend (Next.js), cada uno con su `CLAUDE.md`.
- [ ] Verificar cómo llamar a Jev desde Python (ver decisiones abiertas en `CLAUDE.md`).
- [ ] Endpoint que recibe texto de oferta + CV y devuelve un perfil estructurado (DeepSeek).
- [ ] Endpoint que genera el plan de entrevista a partir del perfil.
- [ ] Endpoint que entrega el token firmado para ElevenLabs.
- [ ] Página mínima: pegar oferta, subir CV, botón de empezar entrevista.
- [ ] Entrevista por voz funcionando de extremo a extremo con DeepSeek como modelo.

Criterio de salida: hago una entrevista completa de Python con mi oferta y mi CV.

## Fase 1: MVP

Objetivo: que otra persona pueda usarlo sin que yo esté delante.

- [ ] Rúbrica derivada de la oferta y puntuación de cada respuesta (Jev o alternativa).
- [ ] Decisión de repreguntar o avanzar según la puntuación.
- [ ] Informe final: notas por criterio, encaje con la oferta, fallos y respuestas modelo.
- [ ] Extracción de texto de CV en PDF y Word.
- [ ] Protección frente a instrucciones inyectadas en CV y oferta.
- [ ] Persistencia de sesiones e informes en Postgres.
- [ ] Borrado de datos al terminar la sesión y aviso de privacidad (RGPD).
- [ ] Despliegue: frontend en Vercel, backend en contenedor.
- [ ] Tests de los endpoints principales.

Criterio de salida: 3 o 4 personas distintas completan una entrevista y el informe les resulta útil.

## Fase 2: Siguiente hito

- [ ] Varias ofertas y CVs por usuario, para preparar procesos en paralelo.
- [ ] Cuentas de usuario.
- [ ] Editor de código en vivo durante la entrevista (ejercicios de Python).
- [ ] Historial de sesiones y progreso.

## Fase 3: Crecimiento

- [ ] Detección de lagunas recurrentes y sesiones de repaso sugeridas.
- [ ] Inglés y otros idiomas.
- [ ] Modelo de pago y límites de uso.
- [ ] Posible oferta para academias y empresas.

## Riesgos a vigilar

- **Latencia de la voz:** la respuesta debe llegar en 1-2 segundos o deja de parecer una entrevista.
- **Coste por minuto:** la voz es lo más caro; calcularlo antes de fijar precios.
- **Fiabilidad de las puntuaciones:** contrastarlas con juicio humano antes de mostrarlas como definitivas.
- **Privacidad:** CVs y transcripciones son datos personales.
- **Nombre:** comprobar dominio y marca (EUIPO) para "Sparring" antes de invertir en branding.
