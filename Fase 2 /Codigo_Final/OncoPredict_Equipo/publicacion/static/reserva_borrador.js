(() => {
  const form = document.querySelector('form[data-borrador-reserva]');
  if (!form) return;

  const clave = 'onco_clinica_reserva_borrador';
  const campos = ['rut', 'nombre', 'edad', 'correo', 'motivo'];
  const leer = () => {
    try {
      const valor = sessionStorage.getItem(clave);
      return valor ? JSON.parse(valor) : null;
    } catch (_) {
      return null;
    }
  };
  const borrador = leer();
  let recuperados = 0;

  if (borrador && typeof borrador === 'object') {
    campos.forEach((nombre) => {
      const campo = form.elements.namedItem(nombre);
      if (campo && !campo.value && typeof borrador[nombre] === 'string' && borrador[nombre]) {
        campo.value = borrador[nombre];
        recuperados += 1;
      }
    });
  }

  const aviso = document.createElement('div');
  aviso.className = 'web-alerta reserva-borrador-aviso';
  aviso.setAttribute('role', 'status');
  aviso.setAttribute('aria-live', 'polite');
  const mensaje = document.createElement('span');
  mensaje.textContent = recuperados
    ? 'Recuperamos los datos que ya habías ingresado en esta pestaña.'
    : 'Tus datos se guardarán temporalmente en esta pestaña mientras completas la reserva.';
  aviso.append(mensaje);
  const borrar = document.createElement('button');
  borrar.className = 'reserva-borrador-borrar';
  borrar.type = 'button';
  borrar.textContent = 'Borrar datos guardados';
  aviso.append(borrar);
  form.prepend(aviso);

  const guardar = () => {
    const datos = {};
    campos.forEach((nombre) => {
      const campo = form.elements.namedItem(nombre);
      if (campo) datos[nombre] = campo.value;
    });
    try {
      sessionStorage.setItem(clave, JSON.stringify(datos));
    } catch (_) {
      // El formulario sigue funcionando si el navegador bloquea el almacenamiento temporal.
    }
  };

  form.addEventListener('input', guardar);
  form.addEventListener('change', guardar);
  form.addEventListener('submit', guardar);
  borrar.addEventListener('click', () => {
    try { sessionStorage.removeItem(clave); } catch (_) {}
    campos.forEach((nombre) => {
      const campo = form.elements.namedItem(nombre);
      if (campo) campo.value = '';
    });
    aviso.remove();
  });
})();
