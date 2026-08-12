/**
 * Tinglish homepage — scroll rail, live call widget, spotlight reveals
 */
(function () {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const LIVE_LINES = [
    "Namaste andi! Nenu Sumeet, Cyberhost nunchi matladutunnanu.",
    "Kokapet lo 3 BHK flat price 1.2 Crores nunchi start avutundi. Site visit schedule cheddama?",
    "Budget entha andi? Gachibowli side kuda chuddacha — Candeur Skyline options unnayi.",
    "Financial District lo ASBL Broadway — 2 BHK 95 lakhs nunchi. Brochure WhatsApp lo pampistha.",
    "Sare andi, Saturday 11 AM ki site visit book chesanu. CRM lo update chesanu — rep follow-up chestaru.",
  ];

  const progressFill = document.getElementById("scroll-progress-fill");
  const sectionRail = document.getElementById("section-rail");
  const liveCall = document.getElementById("live-call");
  const liveBubble = document.getElementById("live-bubble");
  const stage = document.getElementById("scrub-stage");
  const marquee = document.getElementById("project-marquee");

  let liveLineIndex = 0;
  let liveRotateTimer = null;
  let demoPlaying = false;

  /* duplicate marquee for seamless loop */
  if (marquee && !reducedMotion) {
    marquee.innerHTML += marquee.innerHTML;
  }

  /* spotlight reveals */
  function initReveals() {
    const targets = document.querySelectorAll(".tl-reveal");
    if (!targets.length) return;

    if (reducedMotion) {
      targets.forEach((el) => el.classList.add("is-visible"));
      return;
    }

    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            obs.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -32px 0px" }
    );
    targets.forEach((el) => obs.observe(el));
  }

  /* live call floater */
  function showLiveCall() {
    liveCall?.classList.add("is-visible");
    startLiveRotate();
  }

  function rotateLiveLine() {
    if (!liveBubble) return;
    liveBubble.classList.add("is-fading");
    setTimeout(() => {
      liveLineIndex = (liveLineIndex + 1) % LIVE_LINES.length;
      liveBubble.textContent = LIVE_LINES[liveLineIndex];
      liveBubble.classList.remove("is-fading");
    }, 280);
  }

  function startLiveRotate() {
    if (reducedMotion || liveRotateTimer) return;
    liveRotateTimer = setInterval(rotateLiveLine, 5200);
  }

  function stopLiveRotate() {
    if (liveRotateTimer) {
      clearInterval(liveRotateTimer);
      liveRotateTimer = null;
    }
  }

  /* section rail */
  const SECTION_MAP = {
    hero: { start: 0, end: 0.15 },
    ring: { start: 0.15, end: 0.35 },
    answer: { start: 0.35, end: 0.6 },
    book: { start: 0.6, end: 0.85 },
    trust: { start: 0.85, end: 0.95 },
  };

  function scrollProgress() {
    if (!stage) return 0;
    const rect = stage.getBoundingClientRect();
    const scrollable = stage.offsetHeight - window.innerHeight;
    if (scrollable <= 0) return 0;
    return Math.max(0, Math.min(1, -rect.top / scrollable));
  }

  function updateScrollUI() {
    const progress = scrollProgress();
    const spotlight = document.getElementById("spotlight");
    const login = document.getElementById("login");

    let totalProgress = progress;
    if (spotlight && login) {
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const globalProgress = docHeight > 0 ? window.scrollY / docHeight : 0;
      totalProgress = globalProgress;
    }

    if (progressFill) {
      progressFill.style.width = `${totalProgress * 100}%`;
    }

    let activeSection = "hero";
    Object.entries(SECTION_MAP).forEach(([id, range]) => {
      if (progress >= range.start && progress < range.end) activeSection = id;
    });

    sectionRail?.querySelectorAll(".tl-section-dot").forEach((dot) => {
      dot.classList.toggle("is-active", dot.dataset.section === activeSection);
    });
  }

  function scrollToSection(sectionId) {
    const range = SECTION_MAP[sectionId];
    if (!range || !stage) return;
    const scrollable = stage.offsetHeight - window.innerHeight;
    const target = range.start * scrollable + stage.offsetTop;
    window.scrollTo({ top: target, behavior: reducedMotion ? "auto" : "smooth" });
  }

  sectionRail?.querySelectorAll(".tl-section-dot").forEach((dot) => {
    dot.addEventListener("click", () => scrollToSection(dot.dataset.section));
  });

  /* sync live bubble with voice demo */
  function setLiveLine(text) {
    if (!liveBubble) return;
    liveBubble.textContent = text;
    liveLineIndex = LIVE_LINES.indexOf(text);
    if (liveLineIndex < 0) liveLineIndex = 0;
  }

  function setDemoPlaying(playing) {
    demoPlaying = playing;
    liveCall?.classList.toggle("is-playing", playing);
    document.querySelectorAll("[data-hear-demo], #btn-hear-demo").forEach((btn) => {
      btn.classList.toggle("is-playing", playing);
      if (btn.id === "btn-hear-demo") {
        const label = playing ? "Playing…" : "Hear Sumeet Talk";
        const icon = btn.querySelector(".tl-btn-icon");
        btn.childNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE) node.textContent = "";
        });
        if (icon) {
          btn.innerHTML = "";
          btn.appendChild(icon);
          btn.append(` ${label}`);
        } else {
          btn.textContent = label;
        }
      }
    });
    if (playing) {
      stopLiveRotate();
      showLiveCall();
    } else {
      startLiveRotate();
    }
  }

  window.addEventListener("scrub:frames-ready", () => {
    setTimeout(showLiveCall, 1200);
  });

  window.addEventListener("tinglish:demo-start", (e) => {
    if (e.detail?.line) setLiveLine(e.detail.line);
    setDemoPlaying(true);
  });

  window.addEventListener("tinglish:demo-end", () => {
    setDemoPlaying(false);
  });

  window.addEventListener("tinglish:demo-line", (e) => {
    if (e.detail?.line) setLiveLine(e.detail.line);
  });

  window.addEventListener("scroll", updateScrollUI, { passive: true });
  window.addEventListener("resize", updateScrollUI);

  initReveals();
  updateScrollUI();

  if (reducedMotion) showLiveCall();
})();