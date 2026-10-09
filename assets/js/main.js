(function () {
  'use strict';

  var root = document.documentElement;
  var FAIXA_CLASS = { 'C': 'f-c', 'C+': 'f-cp', 'B': 'f-b', 'B+': 'f-bp', 'A': 'f-a' };
  var FAIXAS = ['C', 'C+', 'B', 'B+', 'A'];

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function fmt(value, decimals) {
    return value.toFixed(decimals).replace('.', ',');
  }

  function fmtPP(value) {
    var v = Math.round(value * 100) / 100;
    var oneDecimal = Math.abs(v * 10 - Math.round(v * 10)) < 1e-9;
    return fmt(v, oneDecimal ? 1 : 2);
  }

  function fmtPct(score) {
    var v = Math.round(score * 10) / 10;
    return (Number.isInteger(v) ? String(v) : fmt(v, 1)) + '%';
  }

  function faixaOf(percent) {
    if (percent >= 90) return 'A';
    if (percent >= 75) return 'B+';
    if (percent >= 60) return 'B';
    if (percent >= 50) return 'C+';
    return 'C';
  }

  /* Theme: automatic, light or dark, remembered per viewer when storage works. */
  var THEME_KEY = 'faixa-previa-tema';
  var THEME_LABEL = { auto: ['Auto', 'automático'], light: ['Claro', 'claro'], dark: ['Escuro', 'escuro'] };
  var themeBtn = document.getElementById('tema');

  function currentTheme() {
    var t = root.getAttribute('data-theme');
    return t === 'light' || t === 'dark' ? t : 'auto';
  }

  function applyTheme(mode) {
    if (mode === 'light' || mode === 'dark') root.setAttribute('data-theme', mode);
    else root.removeAttribute('data-theme');
    if (themeBtn) {
      themeBtn.querySelector('.theme-l').textContent = THEME_LABEL[mode][0];
      themeBtn.setAttribute('aria-label', 'Tema: ' + THEME_LABEL[mode][1] + '. Trocar tema');
    }
    try {
      if (mode === 'auto') localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, mode);
    } catch (e) { /* storage unavailable: theme still applies for this visit */ }
  }

  if (themeBtn) {
    applyTheme(currentTheme());
    themeBtn.addEventListener('click', function () {
      var next = { auto: 'light', light: 'dark', dark: 'auto' }[currentTheme()];
      applyTheme(next);
    });
  }

  /* Tooltip shared by every chart. */
  var tip = document.getElementById('tip');

  function placeTip(x, y) {
    var r = tip.getBoundingClientRect();
    var left = x + 14;
    var top = y + 14;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
    tip.style.left = Math.max(8, left) + 'px';
    tip.style.top = Math.max(8, top) + 'px';
  }

  function showTip(build, x, y) {
    tip.replaceChildren();
    build(tip);
    tip.hidden = false;
    placeTip(x, y);
  }

  function hideTip() { tip.hidden = true; }

  function anchorOf(node) {
    var r = node.getBoundingClientRect();
    return { x: r.left + Math.min(r.width * 0.6, 260), y: r.top + r.height / 2 };
  }

  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') hideTip(); });
  window.addEventListener('scroll', hideTip, { passive: true });

  /* Stacked rows: one tooltip lists every band of the year. */
  document.querySelectorAll('.stack-row').forEach(function (row) {
    var counts = JSON.parse(row.dataset.counts);
    var ano = row.dataset.ano;

    function build(active) {
      return function (box) {
        box.appendChild(el('div', 'tip-t', 'Ano-base ' + ano));
        var list = el('div', 'tip-rows');
        FAIXAS.slice().reverse().forEach(function (f) {
          var line = el('div', 'tip-row' + (f === active ? ' is-on' : ''));
          line.appendChild(el('i', FAIXA_CLASS[f]));
          line.appendChild(el('span', '', f));
          line.appendChild(el('b', '', String(counts[f])));
          list.appendChild(line);
        });
        box.appendChild(list);
      };
    }

    row.addEventListener('pointermove', function (e) {
      var seg = e.target.closest('.seg');
      showTip(build(seg ? seg.dataset.faixa : null), e.clientX, e.clientY);
    });
    row.addEventListener('pointerleave', hideTip);
    row.addEventListener('focus', function () {
      var a = anchorOf(row);
      showTip(build(null), a.x, a.y);
    });
    row.addEventListener('blur', hideTip);
  });

  /* Single-value marks. */
  document.querySelectorAll('[data-tip-title]').forEach(function (mark) {
    function build(box) {
      box.appendChild(el('div', 'tip-t', mark.dataset.tipTitle));
      box.appendChild(el('div', 'tip-v', mark.dataset.tipValue));
    }
    mark.addEventListener('pointermove', function (e) { showTip(build, e.clientX, e.clientY); });
    mark.addEventListener('pointerleave', hideTip);
    mark.addEventListener('focus', function () { var a = anchorOf(mark); showTip(build, a.x, a.y); });
    mark.addEventListener('blur', hideTip);
  });

  /* Small multiples: crosshair snaps to the nearest year; arrow keys move it. */
  var LO = 0.2;
  var HI = 0.9;
  document.querySelectorAll('.sm-plot').forEach(function (plot) {
    var series = JSON.parse(plot.dataset.series);
    var years = JSON.parse(plot.dataset.years);
    var name = plot.dataset.name;
    var n = series.length;
    var cross = plot.querySelector('.sm-cross');
    var dot = el('span', 'sm-hdot');
    dot.hidden = true;
    plot.appendChild(dot);
    var index = n - 1;

    function yPct(v) { return (HI - v) / (HI - LO) * 100; }

    function render(i, x, y) {
      index = i;
      var left = i / (n - 1) * 100;
      cross.hidden = false;
      cross.style.left = left + '%';
      dot.hidden = false;
      dot.style.left = left + '%';
      dot.style.top = yPct(series[i]) + '%';
      var value = series[i] * 100;
      showTip(function (box) {
        box.appendChild(el('div', 'tip-t', name + ', ano-base ' + years[i]));
        box.appendChild(el('div', 'tip-v', fmt(value, 1) + '%'));
        box.appendChild(el('div', '', 'Faixa de referência ' + faixaOf(value)));
      }, x, y);
    }

    function clear() {
      cross.hidden = true;
      dot.hidden = true;
      hideTip();
    }

    plot.addEventListener('pointermove', function (e) {
      var r = plot.getBoundingClientRect();
      var frac = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      render(Math.round(frac * (n - 1)), e.clientX, e.clientY);
    });
    plot.addEventListener('pointerleave', clear);
    plot.addEventListener('focus', function () {
      var a = anchorOf(plot);
      render(index, a.x, a.y);
    });
    plot.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      var next = Math.min(n - 1, Math.max(0, index + (e.key === 'ArrowRight' ? 1 : -1)));
      var a = anchorOf(plot);
      render(next, a.x, a.y);
    });
    plot.addEventListener('blur', clear);
  });

  /* Simulators. */
  function checkedItems(scope) {
    var total = 0;
    var byType = { norma: 0, processo: 0, investimento: 0 };
    scope.querySelectorAll('input[type="checkbox"][data-pp]').forEach(function (box) {
      if (!box.checked) return;
      var pp = parseFloat(box.dataset.pp);
      total += pp;
      byType[box.dataset.tipo] += pp;
    });
    return { total: Math.round(total * 100) / 100, byType: byType };
  }

  function out(scope, key) { return scope.querySelector('[data-out="' + key + '"]'); }

  document.querySelectorAll('[data-sim="nota"]').forEach(function (sim) {
    var slider = sim.querySelector('input[type="range"]');
    var shown = sim.querySelector('output');
    var pinNow = sim.querySelector('[data-pin="atual"]');
    var pinNew = sim.querySelector('[data-pin="nova"]');

    function update() {
      var atual = parseFloat(slider.value);
      var sel = checkedItems(sim);
      var nova = Math.min(100, atual + sel.total);
      var fa = faixaOf(atual);
      var fn = faixaOf(nova);
      shown.textContent = fmt(atual, 1) + '%';
      out(sim, 'total').textContent = '+' + fmtPP(sel.total) + ' p.p.';
      out(sim, 'nova').textContent = fmt(nova, 1) + '%';
      out(sim, 'faixas').textContent = fa === fn ? 'Continua em ' + fa : fa + ' para ' + fn;
      out(sim, 'tipos').textContent = 'Norma +' + fmtPP(sel.byType.norma) +
        ' · Processo +' + fmtPP(sel.byType.processo) +
        ' · Investimento +' + fmtPP(sel.byType.investimento);
      pinNow.style.setProperty('--p', Math.min(90, Math.max(40, atual)));
      pinNew.style.setProperty('--p', Math.min(90, Math.max(40, nova)));
    }

    sim.addEventListener('input', update);
    sim.addEventListener('change', update);
    update();
  });

  document.querySelectorAll('[data-sim="intervalo"]').forEach(function (sim) {
    var span = sim.querySelector('[data-span="sobe"]');
    var MIN = 60;
    var MAX = 75;

    function update() {
      var sel = checkedItems(sim);
      var threshold = Math.round((MAX - sel.total) * 10) / 10;
      out(sim, 'total').textContent = '+' + fmtPP(sel.total);
      var phrase;
      if (sel.total <= 0) {
        phrase = 'Nenhum item marcado: a faixa continua em B.';
        span.hidden = true;
      } else if (threshold <= MIN) {
        phrase = 'Qualquer nota dentro da faixa B chegaria a B+ com esses pontos.';
        span.hidden = false;
        span.style.setProperty('--a', MIN);
      } else {
        phrase = 'Se a nota atual estiver em ' + fmtPct(threshold) +
          ' ou mais, recuperar esses pontos leva a faixa a B+. Abaixo disso, continua em B.';
        span.hidden = false;
        span.style.setProperty('--a', threshold);
      }
      out(sim, 'frase').textContent = phrase;
    }

    sim.addEventListener('change', update);
    update();
  });

  /* Highlight the section in view on the navigation. */
  var links = {};
  document.querySelectorAll('.nav a[href^="#"]').forEach(function (a) { links[a.getAttribute('href').slice(1)] = a; });
  if ('IntersectionObserver' in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        Object.keys(links).forEach(function (id) { links[id].removeAttribute('aria-current'); });
        var link = links[entry.target.id];
        if (link) {
          link.setAttribute('aria-current', 'true');
          var nav = link.closest('.nav');
          if (nav && nav.scrollWidth > nav.clientWidth) {
            var target = link.offsetLeft - nav.clientWidth / 2 + link.offsetWidth / 2;
            nav.scrollTo({ left: Math.max(0, target) });
          }
        }
      });
    }, { rootMargin: '-40% 0px -55% 0px' });
    document.querySelectorAll('main section[id]').forEach(function (s) { observer.observe(s); });
  }
})();
