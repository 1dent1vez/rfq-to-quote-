import type { IntakeCase } from './types'

export default function CaseView({value}: {value: IntakeCase}) {
  return <section aria-label="Resultado de identificación" className="results">
    <h2>2. Líneas identificadas</h2>
    <p className="case-status">{value.status === 'identified' ? 'Solicitud identificada' : 'Solicitud pendiente'}</p>
    <p>{value.request_id} · {value.customer} · <span className="badge">Transacción ficticia</span></p>
    <details open><summary>Original guardado</summary><pre>{value.email_text}</pre></details>
    {value.lines.map(line => <article key={line.evidence.line} className="line">
      <h3>Línea {line.evidence.line} · {line.mode === 'pieza' ? 'Por referencia' : 'Por vehículo'}</h3>
      <p>{line.status === 'matched' ? 'Identificada' : 'Pendiente'} · Cantidad: {line.quantity ?? 'No válida o faltante'}</p>
      <details><summary>Evidencia de captura · {line.evidence.source === 'seller_form' ? 'formulario del vendedor, no texto interpretado' : 'entrada técnica'}</summary><pre>{line.evidence.text}</pre></details>
      <dl>{Object.entries(line.fields).map(([key, field]) => <div key={key}><dt>{key}</dt><dd>{field || '(vacío)'}</dd></div>)}</dl>
      <p className="notice">{line.compatibility === 'source_catalog_claim_only' ? 'Coincidencia con declaración del catálogo; no garantiza compatibilidad real. Verificar con fabricante antes de instalar.' : line.compatibility === 'synthetic_application_only' ? 'Aplicación histórica sintética; no acredita compatibilidad real.' : line.mode === 'vehiculo' ? 'Aplicación incompleta o ambigua; compatibilidad no evaluada.' : 'Referencia exacta no demuestra compatibilidad vehicular; compatibilidad no evaluada.'}</p>
      <h4>3. Candidatos con evidencia de catálogo</h4>
      {line.candidates.map(candidate => <div className="candidate" key={candidate.id}>
        <strong>{candidate.reference}</strong> <span className="badge">{candidate.source ? 'Fuente fabricante' : 'Histórico sintético'}</span>
        <p>{candidate.description} · {candidate.manufacturer}</p>
        <small>Catálogo: {candidate.id}</small>
        {candidate.source && <><p><a href={candidate.source.url}>GONHER {candidate.source.edition} · página impresa {candidate.source.printed_page}</a></p><p>{candidate.source.claim}</p></>}
        {line.status === 'pending' && <p className="pending">Candidato, no selección automática</p>}
        {candidate.matching_applications?.map((application, index) => <p key={index}>Declaración de aplicación: {application.make} · {application.model} · {application.year} · {application.engine}</p>)}
      </div>)}
      <h4>4. Aclaraciones pendientes</h4>
      {line.missing_fields.length > 0 ? <div className="pending">
        <p>Campos por confirmar: {line.missing_fields.join(', ')}</p>
        <ul>{line.clarifications.map(question => <li key={question}>{question}</li>)}</ul>
        <p>Edite los campos (o el mensaje en modo avanzado) tras confirmar con el cliente y registre una nueva solicitud. Ningún candidato se elige automáticamente.</p>
      </div> : <p>Sin campos pendientes en este subconjunto del catálogo. No es una cotización ni autorización comercial.</p>}
    </article>)}
  </section>
}
