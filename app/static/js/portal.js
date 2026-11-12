/* Resident portal behaviour. Vanilla JS, no inline handlers, no fake success states. */
(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const ICON_SPRITE = "/static/img/icons.svg";
  function makeIcon(name, className = "") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", `icon-svg ${className}`.trim());
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `${ICON_SPRITE}#${name}`);
    svg.appendChild(use);
    return svg;
  }

  $$("[data-portal-year]").forEach((el) => {
    el.textContent = String(new Date().getFullYear());
  });

  $$("[data-portal-today]").forEach((el) => {
    el.textContent = new Intl.DateTimeFormat("en-PH", {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone: "Asia/Manila",
    }).format(new Date());
  });

  /* ---------------- Local dates rendered in Asia/Manila ---------------- */
  const dateOptions = {
    datetime: { year: "numeric", month: "short", day: "2-digit", hour: "numeric", minute: "2-digit" },
    date: { year: "numeric", month: "short", day: "2-digit" },
    time: { hour: "numeric", minute: "2-digit" },
  };

  $$("time[datetime]").forEach((el) => {
    let raw = el.getAttribute("datetime");
    if (!raw) return;
    // Timestamps are stored in UTC; SQLite returns them without an offset.
    if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)) raw = `${raw.replace(" ", "T")}Z`;
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.valueOf())) return;
    const mode = el.dataset.fmt === "date" ? "date" : el.dataset.fmt === "time" ? "time" : "datetime";
    el.textContent = new Intl.DateTimeFormat("en-PH", { ...dateOptions[mode], timeZone: "Asia/Manila" }).format(parsed);
  });

  /* ---------------- Toasts from server flashes ---------------- */
  const toastHost = $("#portal-toast");

  function showToast(message, category) {
    if (!toastHost) return;
    const isError = ["danger", "error", "warning"].includes(category);
    const card = document.createElement("div");
    card.className = `pointer-events-auto flex items-start gap-2.5 rounded-xl border bg-surface-card p-3.5 shadow-lg ${
      isError ? "border-error/40" : "border-highlight-lime"
    }`;
    const icon = makeIcon(isError ? "exclamation-triangle" : "check-circle", "shrink-0");
    icon.style.width = "20px";
    icon.style.height = "20px";
    icon.style.color = isError ? "#d93025" : "#006b1b";
    const text = document.createElement("p");
    text.className = "text-body-sm text-on-surface flex-1";
    text.textContent = message;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "text-outline hover:text-on-surface";
    close.setAttribute("aria-label", "Isara ang abiso");
    close.appendChild(makeIcon("x-lg"));
    close.querySelector("svg").style.cssText = "width:18px;height:18px";
    close.addEventListener("click", () => card.remove());
    card.append(icon, text, close);
    toastHost.append(card);
    setTimeout(() => card.remove(), 6000);
  }

  $$("[data-portal-flashes] [data-flash-category]").forEach((item, index) => {
    setTimeout(() => showToast(item.textContent.trim(), item.dataset.flashCategory), index * 180);
  });

  /* ---------------- Dropdowns ---------------- */
  $$("[data-portal-dropdown]").forEach((wrapper) => {
    const trigger = $("[data-portal-dropdown-trigger]", wrapper);
    const panel = $("[data-portal-dropdown-panel]", wrapper);
    if (!trigger || !panel) return;

    const close = () => {
      panel.classList.add("hidden");
      trigger.setAttribute("aria-expanded", "false");
    };

    trigger.addEventListener("click", (event) => {
      event.stopPropagation();
      const wasOpen = !panel.classList.contains("hidden");
      document.querySelectorAll("[data-portal-dropdown]").forEach(other => {
        if (other === wrapper) return;
        other.querySelector("[data-portal-dropdown-panel]")?.classList.add("hidden");
        other.querySelector("[data-portal-dropdown-trigger]")?.setAttribute("aria-expanded", "false");
      });
      panel.classList.toggle("hidden", wasOpen);
      trigger.setAttribute("aria-expanded", wasOpen ? "false" : "true");
    });

    document.addEventListener("click", (event) => {
      if (!wrapper.contains(event.target)) close();
    });

    wrapper.addEventListener("keydown", event => {
      const items = [...panel.querySelectorAll('a[href],button:not(:disabled),[role="menuitem"]')].filter(item => !item.closest('[hidden]'));
      if (event.key === "Escape") { close(); trigger.focus(); return; }
      if (!["ArrowDown","ArrowUp","Home","End"].includes(event.key) || !items.length) return;
      event.preventDefault(); panel.classList.remove("hidden"); trigger.setAttribute("aria-expanded","true");
      const current = items.indexOf(document.activeElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length-1 : event.key === "ArrowDown" ? (current+1)%items.length : current<=0 ? items.length-1 : current-1;
      items[next].focus();
    });
    wrapper.addEventListener("focusout",event => { if (!wrapper.contains(event.relatedTarget)) close(); });
  });

  /* ---------------- Modal ---------------- */
  const modal = $("#portal-modal");
  const modalBox = $("[data-portal-modal-box]", modal || document);
  const modalTitle = $("#portal-modal-title");
  const signoutForm = $("[data-portal-signout-form]");
  const titles = {
    privacy: "Karapatan sa Data Privacy",
    help: "Barangay Help Desk",
    charter: "Citizen's Charter",
    signout: "Kumpirmahin ang pag-sign out",
  };
  let lastTrigger = null;

  function openModal(key, trigger) {
    if (!modal) return;
    lastTrigger = trigger || null;
    $$("[data-portal-panel]", modal).forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.portalPanel !== key);
    });
    if (modalTitle) modalTitle.textContent = titles[key] || "Paunawa";
    if (signoutForm) signoutForm.classList.toggle("hidden", key !== "signout");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    document.body.style.overflow = "hidden";
    const focusables = $$("button, [href], input, select, textarea", modalBox).filter((el) => !el.disabled && el.offsetParent !== null);
    (focusables[0] || modalBox)?.focus?.();
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    document.body.style.overflow = "";
    lastTrigger?.focus?.();
  }

  $$("[data-portal-modal]").forEach((trigger) => {
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      openModal(trigger.dataset.portalModal, trigger);
    });
  });

  $$("[data-portal-modal-close]").forEach((button) => button.addEventListener("click", closeModal));
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  document.addEventListener("keydown", (event) => {
    if (!modal || modal.classList.contains("hidden")) return;
    if (event.key === "Escape") {
      closeModal();
      return;
    }
    if (event.key !== "Tab" || !modalBox) return;
    const focusables = $$("button, [href], input, select, textarea", modalBox).filter((el) => !el.disabled && el.offsetParent !== null);
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  /* ---------------- Mobile sidebar drawer ---------------- */
  const sidebar = $("#portal-sidebar");
  const backdrop = $("[data-portal-drawer-backdrop]");
  const drawerOpen = $("[data-portal-drawer-open]");

  let drawerActive = false;
  let drawerReturnFocus = null;
  let previousOverflow = '';
  const drawerItems = () => [...(sidebar?.querySelectorAll('a[href], button:not(:disabled), [tabindex="0"]') || [])]
    .filter(item => item.getClientRects().length && !item.closest('[hidden]'));
  function setDrawer(open, restoreFocus = true) {
    if (!sidebar || !backdrop || open === drawerActive) return;
    if (open) {
      drawerReturnFocus = document.activeElement;
      previousOverflow = document.body.style.overflow;
    }
    drawerActive = open;
    ['max-md:hidden', 'max-lg:hidden', 'max-xl:hidden'].forEach(cls => sidebar.classList.toggle(cls, !open));
    backdrop.classList.toggle('hidden', !open);
    drawerOpen?.setAttribute('aria-expanded', String(open));
    document.body.style.overflow = open ? 'hidden' : previousOverflow;
    if (open) {
      sidebar.setAttribute('role', 'dialog');
      sidebar.setAttribute('aria-modal', 'true');
      sidebar.setAttribute('aria-label', 'Navigation');
      drawerItems()[0]?.focus();
    } else {
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
      if (restoreFocus) drawerReturnFocus?.focus();
    }
  }
  drawerOpen?.addEventListener('click', () => setDrawer(true));
  $$('[data-portal-drawer-close]').forEach(button => button.addEventListener('click', () => setDrawer(false)));
  backdrop?.addEventListener('click', () => setDrawer(false));
  document.addEventListener('keydown', event => {
    if (!drawerActive) return;
    if (event.key === 'Escape') { event.preventDefault(); setDrawer(false); }
    if (event.key === 'Tab') {
      const items = drawerItems(), first = items[0], last = items.at(-1);
      if (!first) return;
      if (event.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    }
  });
  window.addEventListener('resize', () => { if (innerWidth >= 768) setDrawer(false, false); });

  /* ---------------- Dismissible advisory banner ---------------- */
  $$("[data-portal-dismiss]").forEach((button) => {
    const banner = button.closest("[data-portal-banner]");
    const key = banner?.dataset.portalBanner;
    if (!banner || !key) return;
    try {
      if (window.localStorage.getItem(`portal-banner-dismissed:${key}`) === "1") banner.classList.add("hidden");
    } catch (error) {
      /* storage unavailable; banner simply stays visible */
    }
    button.addEventListener("click", () => {
      banner.classList.add("hidden");
      try {
        window.localStorage.setItem(`portal-banner-dismissed:${key}`, "1");
      } catch (error) {
        /* ignore */
      }
    });
  });

  /* ---------------- Client-side filters and helpers ---------------- */
  $$("[data-portal-filter-unread]").forEach((toggle) => {
    toggle.addEventListener("change", () => {
      $$("[data-notification-item]").forEach((item) => {
        item.classList.toggle("hidden", toggle.checked && item.dataset.notificationRead === "1");
      });
    });
  });

  $$("[data-portal-prefill]").forEach((button) => {
    button.addEventListener("click", () => {
      const select = $(button.dataset.portalPrefillTarget || "#document_type_id");
      const value = button.dataset.portalPrefill;
      if (!select || !value) return;
      const match = [...select.options].some((option) => option.value === value);
      if (!match) return;
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      select.focus();
    });
  });

  $$("[data-portal-print]").forEach((button) => button.addEventListener("click", () => window.print()));

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-confirm]");
    if (!form || event.defaultPrevented || form.dataset.confirmed === "1") return;
    event.preventDefault();
    if (form.dataset.confirmPending) return;
    if (!window.confirm(form.dataset.confirm || "Kumpirmahin?")) return;
    const submitter = event.submitter;
    form.dataset.confirmPending = "1";
    setTimeout(() => {
      delete form.dataset.confirmPending;
      form.dataset.confirmed = "1";
      try {
        if (form.requestSubmit) form.requestSubmit(submitter || undefined);
        else form.submit();
      } finally {
        delete form.dataset.confirmed;
      }
    }, 0);
  }, true);

  $$("[data-portal-filter-rows]").forEach((input) => {
    input.addEventListener("input", () => {
      const needle = input.value.trim().toLowerCase();
      const table = document.querySelector(input.dataset.portalFilterRows || "table");
      if (!table) return;
      table.querySelectorAll("tbody tr").forEach((row) => {
        row.classList.toggle("hidden", needle.length > 0 && !row.textContent.toLowerCase().includes(needle));
      });
    });
  });

  $$("[data-portal-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.querySelector(button.dataset.portalToggle);
      if (!target) return;
      target.classList.toggle("hidden");
    });
  });

  $$("[data-export-report]").forEach((button) => {
    button.addEventListener("click", () => {
      const kind = $("#report-kind")?.value;
      const format = button.dataset.exportReport;
      if (!kind || !format) return;
      const query = new URLSearchParams();
      const start = $("#report-start")?.value;
      const end = $("#report-end")?.value;
      if (start) query.set("start", start);
      if (end) query.set("end", end);
      window.location.href = `${button.dataset.exportBase || ""}/export/${kind}/${format}?${query.toString()}`;
    });
  });
})();
