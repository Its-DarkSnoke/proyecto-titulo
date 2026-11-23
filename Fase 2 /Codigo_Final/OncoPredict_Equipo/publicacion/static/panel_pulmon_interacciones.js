(() => {
  const init = () => {
    const body = document.body;
    if (!body.classList.contains('panel-medico')) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const progress = document.createElement('div');
    progress.className = 'panel-progreso';
    progress.setAttribute('aria-hidden', 'true');
    progress.innerHTML = '<span></span>';
    body.append(progress);

    const controls = document.createElement('div');
    controls.className = 'panel-controles';
    controls.innerHTML = '<button class="panel-texto" type="button" aria-label="Aumentar tamaño del texto" aria-pressed="false" title="Aumentar tamaño del texto">A+</button><button class="panel-volver-arriba" type="button" aria-label="Volver arriba" title="Volver arriba">↑</button>';
    body.append(controls);

    const fill = progress.querySelector('span');
    const toTop = controls.querySelector('.panel-volver-arriba');
    const textSize = controls.querySelector('.panel-texto');
    const updateScroll = () => {
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      const amount = maxScroll > 0 ? window.scrollY / maxScroll : 0;
      fill.style.transform = `scaleX(${Math.max(0, Math.min(1, amount))})`;
      toTop.classList.toggle('visible', window.scrollY > 420);
    };
    window.addEventListener('scroll', updateScroll, { passive: true });
    window.addEventListener('resize', updateScroll, { passive: true });
    updateScroll();

    toTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: reducedMotion ? 'auto' : 'smooth' }));
    textSize.addEventListener('click', () => {
      const active = body.classList.toggle('texto-ampliado');
      textSize.setAttribute('aria-pressed', String(active));
      textSize.setAttribute('aria-label', active ? 'Restablecer tamaño del texto' : 'Aumentar tamaño del texto');
      textSize.title = active ? 'Restablecer tamaño del texto' : 'Aumentar tamaño del texto';
    });

    const nav = body.querySelector('.lateral nav');
    const sectionLinks = [...nav.querySelectorAll('a[href^="#"]')];
    const setActive = (sectionId) => {
      const match = sectionLinks.find((link) => link.hash === `#${sectionId}`);
      sectionLinks.forEach((link) => {
        const active = link === match;
        link.classList.toggle('nav-activo', active);
        if (active) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
      if (!match) {
        const summary = nav.querySelector('a:not([href^="#"])');
        if (summary) {
          summary.classList.add('nav-activo');
          summary.setAttribute('aria-current', 'page');
        }
      } else {
        const summary = nav.querySelector('a:not([href^="#"])');
        summary?.classList.remove('nav-activo');
        summary?.removeAttribute('aria-current');
      }
    };
    sectionLinks.forEach((link) => link.addEventListener('click', () => setActive(link.hash.slice(1))));
    if ('IntersectionObserver' in window) {
      const sections = sectionLinks.map((link) => document.querySelector(link.hash)).filter(Boolean);
      const observer = new IntersectionObserver((entries) => {
        const current = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (current) setActive(current.target.id);
      }, { rootMargin: '-18% 0px -65% 0px', threshold: [0, .15, .4, .7] });
      sections.forEach((section) => observer.observe(section));

      if (!reducedMotion) {
        body.classList.add('panel-revelado');
        const items = body.querySelectorAll('.encabezado, .indicadores .indicador, #powerbi, #modelo, #pacientes');
        const revealObserver = new IntersectionObserver((entries, currentObserver) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add('panel-visible');
              currentObserver.unobserve(entry.target);
            }
          });
        }, { threshold: .12 });
        items.forEach((item, index) => {
          item.classList.add('panel-entrada');
          item.style.setProperty('--panel-delay', `${Math.min(index, 5) * 65}ms`);
          revealObserver.observe(item);
        });
      }
    }

    const search = document.getElementById('buscar');
    const rows = [...document.querySelectorAll('[data-paciente]')];
    if (search) {
      const feedback = document.createElement('output');
      feedback.className = 'busqueda-feedback';
      feedback.hidden = true;
      search.insertAdjacentElement('afterend', feedback);
      search.addEventListener('input', () => {
        const query = search.value.trim();
        feedback.hidden = !query;
        if (!query) return;
        const visible = rows.filter((row) => !row.hidden).length;
        feedback.textContent = `${visible} ${visible === 1 ? 'paciente encontrado' : 'pacientes encontrados'}`;
      });
      search.addEventListener('search', () => search.dispatchEvent(new Event('input')));
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
