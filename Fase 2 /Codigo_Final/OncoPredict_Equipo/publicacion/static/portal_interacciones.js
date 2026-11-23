(() => {
  const init = () => {
    const body = document.body;
    const ficha = body.querySelector('.ficha-layout');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (ficha) {
      const progress = document.createElement('div');
      progress.className = 'ficha-progreso';
      progress.setAttribute('aria-hidden', 'true');
      progress.innerHTML = '<span></span>';
      body.append(progress);

      const controls = document.createElement('div');
      controls.className = 'ficha-controles';
      controls.innerHTML = '<button class="ficha-control ficha-texto" type="button" aria-label="Aumentar tamaño del texto" aria-pressed="false" title="Aumentar tamaño del texto">A+</button><button class="ficha-control ficha-volver-arriba" type="button" aria-label="Volver arriba" title="Volver arriba">↑</button>';
      body.append(controls);

      const topButton = controls.querySelector('.ficha-volver-arriba');
      const textButton = controls.querySelector('.ficha-texto');
      const fill = progress.querySelector('span');
      const update = () => {
        const scrollable = document.documentElement.scrollHeight - window.innerHeight;
        fill.style.transform = `scaleX(${scrollable > 0 ? Math.min(1, window.scrollY / scrollable) : 0})`;
        topButton.classList.toggle('visible', window.scrollY > 350);
      };
      window.addEventListener('scroll', update, { passive: true });
      window.addEventListener('resize', update, { passive: true });
      update();

      topButton.addEventListener('click', () => window.scrollTo({ top: 0, behavior: reducedMotion ? 'auto' : 'smooth' }));
      textButton.addEventListener('click', () => {
        const active = body.classList.toggle('ficha-texto-ampliado');
        textButton.setAttribute('aria-pressed', String(active));
        textButton.setAttribute('aria-label', active ? 'Restablecer tamaño del texto' : 'Aumentar tamaño del texto');
        textButton.title = active ? 'Restablecer tamaño del texto' : 'Aumentar tamaño del texto';
      });

      if (!reducedMotion && 'IntersectionObserver' in window) {
        body.classList.add('ficha-revelada');
        const items = ficha.querySelectorAll('.ficha-cabecera, .resumen-paciente-card, .tarjeta-resultados, .evaluacion, .estado-vacio-paciente');
        const observer = new IntersectionObserver((entries, currentObserver) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add('visible');
              currentObserver.unobserve(entry.target);
            }
          });
        }, { threshold: .12, rootMargin: '0px 0px -20px 0px' });
        items.forEach((item, index) => {
          item.classList.add('ficha-revelar');
          item.style.setProperty('--retraso-ficha', `${Math.min(index, 4) * 65}ms`);
          observer.observe(item);
        });
      }
    }

    body.querySelectorAll('form[data-feedback-carga]').forEach((form) => {
      form.addEventListener('submit', (event) => {
        if (form.hasAttribute('data-confirmar-publicacion') && !window.confirm('¿Confirmas que deseas publicar este resultado para el paciente?')) {
          event.preventDefault();
          return;
        }
        const submit = event.submitter || form.querySelector('button[type="submit"],button:not([type])');
        if (submit) {
          submit.setAttribute('aria-busy', 'true');
          submit.disabled = true;
        }
      });
    });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
