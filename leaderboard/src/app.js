/* TS-Bench site: the field of attempts, its tooltip, and two small reveals. No dependencies. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var data = JSON.parse(document.getElementById("data").textContent);
  var models = data.models;
  var insts = data.instances;
  var stage = document.getElementById("stage");
  var tip = document.getElementById("tip");

  var OUTCOME = {
    0: "Did not fix the bug",
    1: "Fixed the bug",
    2: "Tests ran out of time",
    3: "Patch would not apply",
  };
  var RESULT_LANES = [
    [1, "Fixed"],
    [0, "Not fixed"],
    [2, "Timed out"],
    [3, "Patch did not apply"],
  ];

  function taskName(i) {
    var m = /^(.*)-(\d+)$/.exec(insts[i].id);
    return m ? insts[i].repo + " #" + m[2] : insts[i].id;
  }

  // one element per attempt
  var cells = data.attempts.map(function (a, idx) {
    var el = document.createElement("i");
    el.className = "cell c" + a[3];
    el.dataset.idx = idx;
    stage.appendChild(el);
    return { m: a[0], i: a[1], rep: a[2], code: a[3], el: el };
  });

  function group(mode) {
    var lanes = [];
    if (mode === "model") {
      models.forEach(function (m, mi) {
        var list = cells.filter(function (c) { return c.m === mi; });
        if (list.length) lanes.push({ label: m.name, list: list });
      });
    } else if (mode === "repo") {
      var repos = {};
      cells.forEach(function (c) {
        var r = insts[c.i].repo;
        (repos[r] = repos[r] || []).push(c);
      });
      Object.keys(repos).sort().forEach(function (r) { lanes.push({ label: r, list: repos[r] }); });
    } else {
      RESULT_LANES.forEach(function (rl) {
        var list = cells.filter(function (c) { return c.code === rl[0]; });
        if (list.length) lanes.push({ label: rl[1], list: list });
      });
    }
    lanes.forEach(function (lane) {
      lane.list.sort(function (a, b) { return a.m - b.m || a.i - b.i || a.rep - b.rep; });
      var fixed = lane.list.filter(function (c) { return c.code === 1; }).length;
      lane.meta = fixed + " of " + lane.list.length + " fixed";
    });
    return lanes;
  }

  var labels = [];
  var mode = "model";
  var wanted = new URLSearchParams(window.location.search).get("group");
  if (wanted === "repo" || wanted === "result") {
    mode = wanted;
    document.querySelectorAll("[data-group]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.group === mode));
    });
  }

  function metrics() {
    var cs = getComputedStyle(stage);
    return {
      size: parseFloat(cs.getPropertyValue("--cell")) || 12,
      gap: parseFloat(cs.getPropertyValue("--gap")) || 3,
      width: stage.clientWidth,
    };
  }

  // animate: "reveal" fades squares in place in order; "move" glides them to a new grouping; false = instant
  function layout(animate) {
    var mt = metrics();
    var step = mt.size + mt.gap;
    var cols = Math.max(1, Math.floor((mt.width + mt.gap) / step));
    var lanes = group(mode);
    var y = 0;
    var order = 0;

    labels.forEach(function (l) { l.remove(); });
    labels = [];

    lanes.forEach(function (lane) {
      var lab = document.createElement("p");
      lab.className = "lane-label";
      lab.style.top = y + "px";
      lab.innerHTML = "<b></b><span></span>";
      lab.firstChild.textContent = lane.label;
      lab.lastChild.textContent = lane.meta;
      stage.appendChild(lab);
      labels.push(lab);
      requestAnimationFrame(function () { lab.classList.add("is-in"); });
      y += 26;
      lane.list.forEach(function (c, k) {
        c.tx = (k % cols) * step;
        c.ty = y + Math.floor(k / cols) * step;
        c.order = order++;
      });
      y += Math.ceil(lane.list.length / cols) * step + 26;
    });
    stage.style.height = y - 10 + "px";

    cells.forEach(function (c) {
      var delay = Math.min(c.order * 1.2, 900);
      if (animate === "move") {
        c.el.style.transition = "transform 0.7s cubic-bezier(0.2, 0.8, 0.2, 1) " + delay * 0.6 + "ms";
      } else if (animate === "reveal") {
        c.el.style.transition = "opacity 0.45s ease " + delay + "ms";
      } else {
        c.el.style.transition = "none";
      }
      c.el.style.transform = "translate(" + c.tx + "px," + c.ty + "px)";
      c.el.style.opacity = 1;
    });
  }

  // first paint: position everything at once (invisible), then fade in sequentially
  function start() {
    if (reduce) {
      layout(false);
      return;
    }
    cells.forEach(function (c) { c.el.style.opacity = 0; c.el.style.transition = "none"; });
    var began = false;
    function begin() {
      if (began) return;
      began = true;
      layout(false);
      cells.forEach(function (c) { c.el.style.opacity = 0; });
      void stage.offsetWidth;
      layout("reveal");
    }
    // Begin when the field is about to be seen, so the reveal isn't wasted off-screen.
    // Three ways in, so the squares can never stay hidden: already on screen, scrolled into view,
    // or (fallback) a timer.
    var top = stage.getBoundingClientRect().top;
    if (top < window.innerHeight * 0.85) {
      begin();
      return;
    }
    if ("IntersectionObserver" in window) {
      var io0 = new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting) { io0.disconnect(); begin(); }
      }, { rootMargin: "0px 0px -15% 0px" });
      io0.observe(stage);
    }
    setTimeout(begin, 6000);
  }

  var buttons = document.querySelectorAll("[data-group]");
  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      if (mode === b.dataset.group) return;
      mode = b.dataset.group;
      buttons.forEach(function (o) { o.setAttribute("aria-pressed", String(o === b)); });
      layout(reduce ? false : "move");
    });
  });

  var resizeTimer;
  var lastWidth = stage.clientWidth;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (stage.clientWidth !== lastWidth) {
        lastWidth = stage.clientWidth;
        layout(false);
      }
    }, 150);
  });

  // tooltip via event delegation over the stage
  function show(el, x, y) {
    var c = cells[Number(el.dataset.idx)];
    tip.innerHTML = "";
    var b = document.createElement("b");
    b.textContent = models[c.m].name;
    var t = document.createElement("div");
    t.textContent = "Task: " + taskName(c.i);
    var a = document.createElement("div");
    a.textContent = "Attempt " + (c.rep + 1);
    var o = document.createElement("em");
    o.textContent = OUTCOME[c.code];
    tip.appendChild(b);
    tip.appendChild(t);
    tip.appendChild(a);
    tip.appendChild(o);
    tip.classList.add("is-on");
    var w = tip.offsetWidth;
    var left = Math.min(x + 14, window.innerWidth - w - 8);
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = y + 18 + "px";
  }
  stage.addEventListener("pointermove", function (e) {
    var el = e.target.closest && e.target.closest(".cell");
    if (el) show(el, e.clientX, e.clientY);
    else tip.classList.remove("is-on");
  });
  stage.addEventListener("pointerleave", function () { tip.classList.remove("is-on"); });
  window.addEventListener("scroll", function () { tip.classList.remove("is-on"); }, { passive: true });

  // confidence-range bars draw once when scrolled into view
  var ranges = document.querySelectorAll(".range");
  if ("IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add("is-in");
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.6 });
    ranges.forEach(function (r) { io.observe(r); });
  } else {
    ranges.forEach(function (r) { r.classList.add("is-in"); });
  }

  // task matrix: outline the model column under the pointer
  document.querySelectorAll("[data-col]").forEach(function (td) {
    td.addEventListener("mouseenter", function () {
      document.querySelectorAll('[data-col="' + td.dataset.col + '"]').forEach(function (o) { o.classList.add("col-hl"); });
    });
    td.addEventListener("mouseleave", function () {
      document.querySelectorAll(".col-hl").forEach(function (o) { o.classList.remove("col-hl"); });
    });
  });

  start();
})();
