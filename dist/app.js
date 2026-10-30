(() => {
  const root = document.documentElement;
  root.dataset.motionPreference = 'full';
  root.dataset.motionVersion = '20261030-4';
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

  // Explicit keyframes give entrance effects a real start and end frame,
  // including a fast first load. Scrolling itself always remains native.
  if (!('IntersectionObserver' in window)) return;
  const wideScreen = window.matchMedia('(min-width: 701px)');
  const activeAnimations = new Set();
  const clamp = value => Math.min(1, Math.max(0, value));
  let revealObserver;
  let frame = 0;
  let needsMeasure = true;
  let scenes = [];

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
      line.dataset.lineIndex = index;
      line.append(...nodes);
      mask.append(line);
      if (index < lines.length - 1) mask.append(document.createTextNode(' '));
      return mask;
    }));
  }

  function mark(selector, kind = 'reveal', stagger = 0) {
    document.querySelectorAll(selector).forEach((element, index) => {
      element.dataset.motion = kind;
      element.dataset.motionDelay = index * stagger;
    });
  }

  function play(element, keyframes, options) {
    if (!element.animate) return;
    const animation = element.animate(keyframes, {
      duration: 1000, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'both', ...options,
    });
    activeAnimations.add(animation);
    const cleanup = () => {
      activeAnimations.delete(animation);
      animation.cancel();
    };
    animation.addEventListener('finish', cleanup, { once: true });
    animation.addEventListener('cancel', () => activeAnimations.delete(animation), { once: true });
  }

  function reveal(element) {
    if (element.classList.contains('is-visible')) return;
    element.classList.add('is-visible');
    const mobile = !wideScreen.matches;
    const delay = mobile ? 0 : Math.min(240, Number(element.dataset.motionDelay) || 0);
    if (element.dataset.motion === 'lines') {
      element.querySelectorAll('.motion-line-inner').forEach((line, index) => {
        play(line, [{ transform: 'translate3d(0,112%,0)', opacity: 0.2 }, { transform: 'translate3d(0,0,0)', opacity: 1 }],
          { duration: mobile ? 850 : 1150, delay: index * 130 });
      });
    } else if (element.dataset.motion === 'screen') {
      play(element, [
        { opacity: 0.2, clipPath: 'inset(10% 5% 2% 5% round 14px)' },
        { opacity: 1, clipPath: 'inset(0 0 0 0 round 8px)' },
      ], { duration: 1250 });
    } else if (element.dataset.motion === 'logo') {
      play(element, [{ opacity: 0, transform: 'translate3d(0,20px,0)' }, { opacity: 1, transform: 'translate3d(0,0,0)' }],
        { duration: 850, delay });
    } else {
      play(element, [{ opacity: 0, transform: `translate3d(0,${mobile ? 26 : 48}px,0)` }, { opacity: 1, transform: 'translate3d(0,0,0)' }],
        { duration: mobile ? 800 : 1050, delay });
    }
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
    if (!root.classList.contains('motion-ready')) return;
    if (needsMeasure) measureScenes();
    const viewport = document.documentElement.clientHeight;
    const scroll = window.scrollY;
    const strength = wideScreen.matches ? 1 : 0.38;
    scenes.forEach(({ element, top, height }) => {
      const distance = top - scroll;
      if (!height || distance > viewport + 100 || distance + height < -100) return;
      // Keep changing through the screen's entrance, rather than finishing
      // while only its first edge is visible. Layout measurements ignore transforms.
      const progress = clamp((viewport - distance - viewport * 0.06) /
        (viewport * 0.84 + Math.min(height * 0.45, viewport * 0.4)));
      const remaining = 1 - progress * progress * (3 - 2 * progress);
      if (element.matches('.download-section')) {
        element.style.setProperty('--band-scale', (1 - remaining * 0.085 * strength).toFixed(4));
        element.style.setProperty('--band-radius', `${(remaining * 40 * strength).toFixed(2)}px`);
      } else {
        element.style.setProperty('--scene-tilt', `${(wideScreen.matches ? remaining * 7 : 0).toFixed(3)}deg`);
        element.style.setProperty('--scene-scale', (1 - remaining * 0.12 * strength).toFixed(4));
        element.style.setProperty('--scene-y', `${(remaining * 52 * strength).toFixed(2)}px`);
      }
    });
  }

  function requestDraw(measure = false) {
    needsMeasure ||= measure;
    if (!frame && root.classList.contains('motion-ready')) frame = requestAnimationFrame(draw);
  }

  function stopMotion() {
    root.classList.remove('motion-ready');
    revealObserver?.disconnect();
    cancelAnimationFrame(frame);
    frame = 0;
    for (const animation of [...activeAnimations]) animation.cancel();
  }

  function startMotion() {
    stopMotion();
    try {
      revealObserver = new IntersectionObserver(entries => {
        entries.forEach(({ target, isIntersecting }) => {
          if (!isIntersecting) return;
          reveal(target);
          revealObserver.unobserve(target);
        });
      }, { threshold: 0, rootMargin: '0px 0px -9% 0px' });
      root.classList.add('motion-ready');
      document.querySelectorAll('[data-motion]:not(.is-visible)').forEach(element => revealObserver.observe(element));
      requestDraw(true);
    } catch (error) {
      stopMotion();
      console.warn('Downline animations could not start.', error);
    }
  }

  try {
    document.querySelectorAll('h1, h2').forEach(splitLines);
    mark('h1, h2', 'lines');
    mark('.hero > .eyebrow, .hero-aside', 'reveal', 130);
    mark('.platform-row > .eyebrow, .platform-note');
    mark('.platforms li', 'logo', 60);
    mark('.section-heading > .eyebrow, .showcase-heading .eyebrow, .local-section > .eyebrow, .faq > div > .eyebrow, .download-layout > div > .eyebrow');
    mark('.steps article', 'step', 130);
    mark('.source-note, .showcase-heading > p, .tabs, .screen-caption');
    mark('.local-points article', 'reveal', 100);
    mark('.download-option', 'reveal', 110);
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
    if (document.fonts) document.fonts.ready.then(() => requestDraw(true));
    wideScreen.addEventListener('change', () => requestDraw(true));
    document.addEventListener('focusin', event => {
      event.target.closest('[data-motion]')?.classList.add('is-visible');
    });
    startMotion();
  } catch (error) {
    stopMotion();
    console.warn('Downline animations could not start.', error);
  }
})();
