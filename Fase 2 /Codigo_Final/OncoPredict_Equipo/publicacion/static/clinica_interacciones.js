(() => {
  const start = () => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const progress = document.createElement('div');
    progress.className = 'barra-lectura';
    progress.setAttribute('aria-hidden', 'true');
    progress.innerHTML = '<span></span>';
    document.body.append(progress);

    const tools = document.createElement('div');
    tools.className = 'controles-flotantes';
    tools.innerHTML = '<button class="control-flotante control-texto" type="button" aria-label="Aumentar tamaño del texto" aria-pressed="false" title="Aumentar tamaño del texto">A+</button><button class="control-flotante control-arriba" type="button" aria-label="Volver arriba" title="Volver arriba">↑</button>';
    document.body.append(tools);

    const progressFill = progress.querySelector('span');
    const topButton = tools.querySelector('.control-arriba');
    const textButton = tools.querySelector('.control-texto');
    let scheduled = false;

    const updateScroll = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = scrollable > 0 ? window.scrollY / scrollable : 0;
      progressFill.style.transform = `scaleX(${Math.min(1, Math.max(0, ratio))})`;
      topButton.classList.toggle('visible', window.scrollY > 360);
      scheduled = false;
    };

    window.addEventListener('scroll', () => {
      if (!scheduled) {
        scheduled = true;
        window.requestAnimationFrame(updateScroll);
      }
    }, { passive: true });
    window.addEventListener('resize', updateScroll, { passive: true });
    updateScroll();

    topButton.addEventListener('click', () => window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' }));
    textButton.addEventListener('click', () => {
      const enabled = document.body.classList.toggle('texto-ampliado');
      textButton.setAttribute('aria-pressed', String(enabled));
      textButton.setAttribute('aria-label', enabled ? 'Restablecer tamaño del texto' : 'Aumentar tamaño del texto');
      textButton.title = enabled ? 'Restablecer tamaño del texto' : 'Aumentar tamaño del texto';
    });

    if (!reduceMotion && 'IntersectionObserver' in window) {
      const revealItems = document.querySelectorAll('.hero > div, .seccion, .web-alerta, .web-titulo, .resultados-cabecera, .web-horarios > *');
      document.body.classList.add('revelado-activo');
      const observer = new IntersectionObserver((entries, currentObserver) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('ya-visible');
            currentObserver.unobserve(entry.target);
          }
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -24px 0px' });
      revealItems.forEach((item, index) => {
        item.classList.add('revelar');
        item.style.setProperty('--retraso-revelado', `${Math.min(index % 4, 3) * 70}ms`);
        observer.observe(item);
      });
    }

    const visual = document.querySelector('.hero-visual');
    const heroCard = visual?.querySelector('.tarjeta-hero');
    if (visual && heroCard && window.matchMedia('(hover: hover) and (pointer: fine)').matches && !reduceMotion) {
      visual.addEventListener('pointermove', (event) => {
        const bounds = visual.getBoundingClientRect();
        const x = (event.clientX - bounds.left) / bounds.width - 0.5;
        const y = (event.clientY - bounds.top) / bounds.height - 0.5;
        heroCard.style.transform = `rotate(-2deg) rotateX(${y * -5}deg) rotateY(${x * 6}deg) translateY(-3px)`;
      });
      visual.addEventListener('pointerleave', () => { heroCard.style.transform = ''; });
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
