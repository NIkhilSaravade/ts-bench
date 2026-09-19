/* TS-Bench leaderboard: the field of attempts, its tooltip, and the small reveals. No dependencies. */
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
    var i;
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
  // deep link: ?group=repo or ?group=result opens on that grouping
  var wanted = new URLSearchParams(window.location.search).get("group");
  if (wanted === "repo" || wanted === "result") {
    mode = wanted;
    document.querySelectorAll("[data-group]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.group === mode));
    });
  }
  var firstLayout = true;

  function metrics() {
    var cs = getComputedStyle(stage);
    var size = parseFloat(cs.getPropertyValue("--cell")) || 13;
    var gap = parseFloat(cs.getPropertyValue("--gap")) || 3;
    return { size: size, gap: gap, width: stage.clientWidth };
  }

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
        var x = (k % cols) * step;
        var yy = y + Math.floor(k / cols) * step;
        c.tx = x;
        c.ty = yy;
        c.order = order++;
      });
      y += Math.ceil(lane.list.length / cols) * step + 26;
    });
    stage.style.height = y - 10 + "px";

    cells.forEach(function (c) {
      if (animate) {
        c.el.style.transition =
          "transform 0.9s cubic-bezier(0.2, 0.8, 0.2, 1) " + Math.min(c.order * 1.6, 1100) + "ms, opacity 0.5s " + Math.min(c.order * 1.6, 1100) + "ms";
      } else {
        c.el.style.transition = "none";
      }
      c.el.style.opacity = 1;
      c.el.style.transform = "translate(" + c.tx + "px," + c.ty + "px)";
    });
  }

  function scatter() {
    var mt = metrics();
    cells.forEach(function (c) {
      var x = Math.random() * mt.width;
      var y = -60 - Math.random() * 260;
      var r = (Math.random() - 0.5) * 540;
      c.el.style.transition = "none";
      c.el.style.opacity = 0;
      c.el.style.transform = "translate(" + x + "px," + y + "px) rotate(" + r + "deg) scale(0.3)";
    });
    void stage.offsetWidth; // commit the scattered start before animating away from it
  }

  function pulseFixed() {
    cells.forEach(function (c) {
      if (c.code === 1) c.el.classList.add("pulse");
    });
  }

  function start() {
    if (reduce) {
      layout(false);
      return;
    }
    scatter();
    // while squares are still falling across the page they must not catch clicks meant for the buttons
    stage.classList.add("is-settling");
    requestAnimationFrame(function () {
      layout(true);
      setTimeout(pulseFixed, 2100);
      setTimeout(function () { stage.classList.remove("is-settling"); }, 2400);
    });
  }

  // grouping buttons
  var buttons = document.querySelectorAll("[data-group]");
  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      if (mode === b.dataset.group) return;
      mode = b.dataset.group;
      buttons.forEach(function (o) { o.setAttribute("aria-pressed", String(o === b)); });
      cells.forEach(function (c) { c.el.classList.remove("pulse"); });
      layout(!reduce);
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

  // tooltip: event delegation over the stage
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

  // the confidence-range bars draw in once, when they scroll into view
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
