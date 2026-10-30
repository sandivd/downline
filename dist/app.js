(() => {
  const root = document.documentElement;
  const themeButton = document.querySelector('.theme-toggle');
  function setTheme(theme) {
    root.dataset.theme = theme;
    themeButton.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`);
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#171c18' : '#f5f3eb';
  }
  try { setTheme(localStorage.getItem('downline-site-theme') === 'light' ? 'light' : 'dark'); } catch { setTheme('dark'); }
  themeButton.addEventListener('click', () => {
    const theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    setTheme(theme);
    try { localStorage.setItem('downline-site-theme', theme); } catch { /* Theme still works when storage is unavailable. */ }
  });
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let refreshMotion = () => {};
  function selectTab(tab, focus = false) {
    tabs.forEach(item => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
    });
    if (focus) tab.focus();
    refreshMotion();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(tab));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); selectTab(tabs[next], true); }
    });
  });

  // Keep native scrolling. Motion is an enhancement, never a requirement for
  // seeing content or following a download link.
  if (!('IntersectionObserver' in window)) return;
  let revealObserver;
  let frame = 0;
  let needsMeasure = true;
  let scenes = [];
  const wideScreen = window.matchMedia('(min-width: 701px)');
  const clamp = value => Math.min(1, Math.max(0, value));

  function splitLines(heading) {
    const lines = [[]];
    [...heading.childNodes].forEach(node => {
      if (node.nodeName === 'BR') lines.push([]);
      else lines[lines.length - 1].push(node);
    });
    if (lines.length < 2) return;
    heading.classList.add('motion-heading');
    heading.replaceChildren(...lines.map((nodes, index) => {
      const mask = document.createElement('span');
      mask.className = 'motion-line';
      const line = document.createElement('span');
      line.className = 'motion-line-inner';
      line.style.setProperty('--line-index', index);
      line.append(...nodes);
      mask.append(line);
      // A real whitespace node keeps the accessible heading text separated.
      if (index < lines.length - 1) mask.append(document.createTextNode(' '));
      return mask;
    }));
  }

  function mark(selector, kind = 'reveal', stagger = 0) {
    document.querySelectorAll(selector).forEach((element, index) => {
      element.dataset.motion = kind;
      if (stagger) element.style.setProperty('--motion-delay', `${index * stagger}ms`);
    });
  }

  function measureScenes() {
    scenes = [...document.querySelectorAll('[data-motion-scene], .download-section')].map(element => {
      let top = 0;
      for (let parent = element; parent; parent = parent.offsetParent) top += parent.offsetTop;
      return { element, top, height: element.offsetHeight };
    });
    needsMeasure = false;
  }

  function draw() {
    frame = 0;
    if (reducedMotion.matches || !root.classList.contains('motion-ready')) return;
    if (needsMeasure) measureScenes();
    if (!wideScreen.matches) return;
    const viewport = document.documentElement.clientHeight;
    const scroll = window.scrollY;
    scenes.forEach(({ element, top, height }) => {
      const distance = top - scroll;
      if (!height || distance > viewport + 100 || distance + height < -100) return;
      const progress = clamp((viewport - distance) / Math.min(viewport * 0.92, height + viewport * 0.35));
      // Ease out as the screen reaches its reading position. Text in screenshots
      // remains sharp and the frame finishes level, rather than drifting forever.
      const remaining = (1 - progress) ** 2;
      if (element.matches('.download-section')) {
        element.style.setProperty('--band-scale', (1 - remaining * 0.035).toFixed(4));
        element.style.setProperty('--band-radius', `${(remaining * 24).toFixed(2)}px`);
      } else {
        element.style.setProperty('--scene-tilt', `${(remaining * 3.2).toFixed(3)}deg`);
        element.style.setProperty('--scene-scale', (1 - remaining * 0.035).toFixed(4));
        element.style.setProperty('--scene-y', `${(remaining * 18).toFixed(2)}px`);
      }
    });
  }

  function requestDraw(measure = false) {
    needsMeasure ||= measure;
    if (!frame && !reducedMotion.matches && root.classList.contains('motion-ready')) frame = requestAnimationFrame(draw);
  }

  function stopMotion() {
    root.classList.remove('motion-ready');
    revealObserver?.disconnect();
    cancelAnimationFrame(frame);
    frame = 0;
  }

  function startMotion() {
    stopMotion();
    if (reducedMotion.matches) return;
    try {
      revealObserver = new IntersectionObserver(entries => {
        entries.forEach(({ target, isIntersecting }) => {
          if (!isIntersecting) return;
          target.classList.add('is-visible');
          revealObserver.unobserve(target);
        });
      }, { threshold: 0, rootMargin: '0px 0px -7% 0px' });
      document.querySelectorAll('[data-motion]:not(.is-visible)').forEach(element => revealObserver.observe(element));
      root.classList.add('motion-ready');
      requestDraw(true);
    } catch {
      stopMotion();
    }
  }

  try {
    document.querySelectorAll('h1, h2').forEach(splitLines);
    mark('h1, h2', 'lines');
    mark('.hero > .eyebrow, .hero-aside', 'reveal', 110);
    mark('.platform-row > .eyebrow, .platform-note');
    mark('.platforms li', 'logo', 45);
    mark('.section-heading > .eyebrow, .showcase-heading .eyebrow, .local-section > .eyebrow, .faq > div > .eyebrow, .download-layout > div > .eyebrow');
    mark('.steps article', 'step', 85);
    mark('.source-note, .showcase-heading > p, .tabs, .screen-caption');
    mark('.local-points article', 'reveal', 70);
    mark('.download-option', 'reveal', 90);
    mark('.install, .faq-list, .footer');
    mark('.hero-window, .screen-panel .app-window', 'screen');
    document.querySelectorAll('.hero-window, .screen-panel .app-window').forEach(element => {
      element.dataset.motionScene = '';
    });
    refreshMotion = () => requestDraw(true);
    window.addEventListener('scroll', () => requestDraw(), { passive: true });
    window.addEventListener('resize', () => requestDraw(true), { passive: true });
    window.addEventListener('pageshow', () => requestDraw(true));
    window.addEventListener('load', () => requestDraw(true), { once: true });
    reducedMotion.addEventListener('change', startMotion);
    wideScreen.addEventListener('change', () => requestDraw(true));
    // Keyboard and anchor navigation must never land on an invisible control.
    document.addEventListener('focusin', event => {
      const element = event.target.closest('[data-motion]');
      if (element) element.classList.add('is-visible');
    });
    startMotion();
  } catch {
    stopMotion();
  }
})();

