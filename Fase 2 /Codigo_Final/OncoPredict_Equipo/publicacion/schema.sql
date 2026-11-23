-- Esquema final para una base nueva. No actualiza tablas preexistentes.
CREATE TABLE IF NOT EXISTS public.doctores (
 id SERIAL PRIMARY KEY, nombre TEXT NOT NULL, correo TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, especializacion TEXT NOT NULL CHECK(especializacion IN ('mama','pulmon'))
);
CREATE UNIQUE INDEX IF NOT EXISTS doctores_correo_normalizado ON public.doctores(lower(correo));
CREATE TABLE IF NOT EXISTS public.pacientes (
 id SERIAL PRIMARY KEY, rut TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL,
 edad INTEGER NOT NULL CHECK(edad BETWEEN 0 AND 120), correo TEXT NOT NULL UNIQUE, password_hash TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS pacientes_correo_normalizado ON public.pacientes(lower(correo));
CREATE TABLE IF NOT EXISTS public.doctor_paciente (
 doctor_id INTEGER NOT NULL REFERENCES public.doctores(id),
 paciente_id INTEGER NOT NULL REFERENCES public.pacientes(id), PRIMARY KEY(doctor_id,paciente_id)
);
CREATE TABLE IF NOT EXISTS public.evaluaciones (
 id SERIAL PRIMARY KEY, paciente_id INTEGER NOT NULL, doctor_id INTEGER NOT NULL,
 tipo TEXT NOT NULL CHECK(tipo IN ('mama','pulmon')), datos JSONB NOT NULL, resultado TEXT NOT NULL,
 publicada BOOLEAN NOT NULL DEFAULT FALSE, creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(doctor_id,paciente_id) REFERENCES public.doctor_paciente(doctor_id,paciente_id)
);
CREATE TABLE IF NOT EXISTS public.disponibilidad_doctores (
 id SERIAL PRIMARY KEY, doctor_id INTEGER NOT NULL REFERENCES public.doctores(id),
 inicio TIMESTAMPTZ NOT NULL, fin TIMESTAMPTZ NOT NULL, habilitada BOOLEAN NOT NULL DEFAULT TRUE,
 CONSTRAINT disponibilidad_duracion CHECK(fin=inicio+INTERVAL '30 minutes'),
 CONSTRAINT disponibilidad_inicio_turno CHECK(EXTRACT(MINUTE FROM inicio AT TIME ZONE 'America/Santiago') IN (0,30) AND EXTRACT(SECOND FROM inicio)=0),
 CONSTRAINT disponibilidad_doctor_inicio_unico UNIQUE(doctor_id,inicio),
 CONSTRAINT disponibilidad_referencia_unica UNIQUE(id,doctor_id,inicio)
);
CREATE TABLE IF NOT EXISTS public.citas (
 id SERIAL PRIMARY KEY, doctor_id INTEGER NOT NULL REFERENCES public.doctores(id),
 paciente_id INTEGER NOT NULL REFERENCES public.pacientes(id), fecha_hora TIMESTAMPTZ NOT NULL,
 motivo TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'pendiente'
 CHECK(estado IN ('pendiente','confirmada','realizada','cancelada','expirada','no_asistio')),
 observaciones TEXT, creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 disponibilidad_id INTEGER NOT NULL, reserva_vence_en TIMESTAMPTZ,
 CONSTRAINT citas_disponibilidad_fk FOREIGN KEY(disponibilidad_id,doctor_id,fecha_hora)
 REFERENCES public.disponibilidad_doctores(id,doctor_id,inicio),
 CONSTRAINT citas_reserva_pendiente_vence CHECK(estado<>'pendiente' OR reserva_vence_en IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS citas_turno_activo_unico ON public.citas(disponibilidad_id)
 WHERE estado IN ('pendiente','confirmada','realizada','no_asistio');
CREATE TABLE IF NOT EXISTS public.atenciones_clinicas (
 id SERIAL PRIMARY KEY, cita_id INTEGER UNIQUE REFERENCES public.citas(id),
 doctor_id INTEGER NOT NULL REFERENCES public.doctores(id), paciente_id INTEGER NOT NULL REFERENCES public.pacientes(id),
 motivo_consulta TEXT NOT NULL, notas_clinicas TEXT, indicaciones TEXT,
 estado TEXT NOT NULL DEFAULT 'borrador' CHECK(estado IN ('borrador','finalizada')),
 creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, finalizada_en TIMESTAMPTZ,
 CHECK((estado='borrador' AND finalizada_en IS NULL) OR (estado='finalizada' AND finalizada_en IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS public.informes_clinicos (
 id SERIAL PRIMARY KEY, evaluacion_id INTEGER REFERENCES public.evaluaciones(id),
 titulo TEXT NOT NULL, contenido TEXT NOT NULL, recomendaciones TEXT, archivo_pdf TEXT,
 publicado BOOLEAN NOT NULL DEFAULT FALSE, creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 atencion_id INTEGER REFERENCES public.atenciones_clinicas(id),
 estado TEXT NOT NULL DEFAULT 'borrador' CHECK(estado IN ('borrador','emitido')), emitido_en TIMESTAMPTZ,
 CONSTRAINT informe_requiere_origen CHECK(atencion_id IS NOT NULL OR evaluacion_id IS NOT NULL),
 CONSTRAINT informe_estado_fecha CHECK((estado='borrador' AND emitido_en IS NULL) OR (estado='emitido' AND emitido_en IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS public.antecedentes_clinicos (
 id SERIAL PRIMARY KEY, paciente_id INTEGER NOT NULL REFERENCES public.pacientes(id),
 doctor_id INTEGER NOT NULL REFERENCES public.doctores(id),
 tipo TEXT NOT NULL CHECK(tipo IN ('personal','familiar','quirurgico','alergia','medicamento','otro')),
 descripcion TEXT NOT NULL, fecha_antecedente DATE, creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS public.pagos (
 id SERIAL PRIMARY KEY, cita_id INTEGER NOT NULL REFERENCES public.citas(id),
 orden_comercio VARCHAR(64) NOT NULL UNIQUE, proveedor VARCHAR(40) NOT NULL,
 referencia_proveedor TEXT, monto INTEGER NOT NULL CHECK(monto>0),
 moneda VARCHAR(3) NOT NULL DEFAULT 'CLP' CHECK(moneda='CLP'),
 estado TEXT NOT NULL DEFAULT 'pendiente' CHECK(estado IN ('pendiente','aprobado','rechazado','cancelado','expirado','reembolsado')),
 codigo_autorizacion TEXT, creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, aprobado_en TIMESTAMPTZ, reembolsado_en TIMESTAMPTZ,
 CONSTRAINT pagos_fecha_aprobacion CHECK(estado NOT IN ('aprobado','reembolsado') OR aprobado_en IS NOT NULL),
 CONSTRAINT pagos_fecha_reembolso CHECK(estado<>'reembolsado' OR reembolsado_en IS NOT NULL),
 CONSTRAINT pagos_referencia_unica UNIQUE(proveedor,referencia_proveedor)
);
CREATE INDEX IF NOT EXISTS pagos_cita_idx ON public.pagos(cita_id);
CREATE UNIQUE INDEX IF NOT EXISTS pagos_un_aprobado_por_cita ON public.pagos(cita_id) WHERE estado='aprobado';
CREATE TABLE IF NOT EXISTS public.notificaciones (
 id SERIAL PRIMARY KEY, cita_id INTEGER NOT NULL REFERENCES public.citas(id), destinatario TEXT NOT NULL,
 tipo TEXT NOT NULL CHECK(tipo IN ('confirmacion_cita','cancelacion_cita','recordatorio_cita')),
 clave_evento TEXT NOT NULL UNIQUE, estado TEXT NOT NULL DEFAULT 'pendiente'
 CHECK(estado IN ('pendiente','en_proceso','enviada','fallida')),
 intentos INTEGER NOT NULL DEFAULT 0 CHECK(intentos>=0), proximo_intento_en TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
 bloqueada_en TIMESTAMPTZ, enviada_en TIMESTAMPTZ, referencia_proveedor TEXT, ultimo_error TEXT,
 creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT notificacion_fecha_envio CHECK(estado<>'enviada' OR enviada_en IS NOT NULL),
 CONSTRAINT notificacion_bloqueo CHECK(estado<>'en_proceso' OR bloqueada_en IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS notificaciones_cita_idx ON public.notificaciones(cita_id);
CREATE INDEX IF NOT EXISTS notificaciones_pendientes_idx ON public.notificaciones(proximo_intento_en)
 WHERE estado IN ('pendiente','fallida');
