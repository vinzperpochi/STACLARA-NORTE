(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const ICON_SPRITE = "/static/img/icons.svg";
  function setIcon(element, name, className) {
    if (!element) return;
    element.className = `icon-svg ${className || ""}`.trim();
    element.setAttribute("aria-hidden", "true");
    let use = element.querySelector("use");
    if (!use) { use = document.createElementNS("http://www.w3.org/2000/svg", "use"); element.appendChild(use); }
    use.setAttribute("href", `${ICON_SPRITE}#${name}`);
  }

  $$("[data-copyright-year]").forEach((el) => {
    el.textContent = String(new Date().getFullYear());
  });

  const toast = $("#toast-notification");
  const toastTitle = $("#toast-title");
  const toastMessage = $("#toast-message");
  const toastIcon = $("#toast-icon");
  const toastWrap = $("#toast-icon-wrapper");
  const toastCard = $("[data-toast-card]");
  let toastTimer = null;

  function showToast(title, message, category) {
    if (!toast) return;
    const isError = ["danger", "error", "warning"].includes(category);
    if (toastTitle) toastTitle.textContent = title;
    if (toastMessage) toastMessage.textContent = message;
    if (toastIcon) setIcon(toastIcon, isError ? "exclamation-triangle" : "check-circle", "text-lg");
    if (toastWrap) toastWrap.style.backgroundColor = isError ? "#D93025" : "#12902B";
    if (toastCard) toastCard.style.borderColor = isError ? "#D93025" : "#22B33A";
    if (toastTitle) toastTitle.style.color = isError ? "#D93025" : "#12902B";
    toast.classList.remove("translate-y-[-150%]", "opacity-0");
    toast.classList.add("translate-y-0", "opacity-100");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(dismissToast, 5000);
  }

  function dismissToast() {
    if (!toast) return;
    toast.classList.add("translate-y-[-150%]", "opacity-0");
    toast.classList.remove("translate-y-0", "opacity-100");
  }

  $("[data-dismiss-toast]")?.addEventListener("click", dismissToast);

  const flashes = $$("[data-flash-item]");
  flashes.forEach((item, index) => {
    const category = item.dataset.flashCategory || "info";
    const title =
      category === "danger" || category === "error"
        ? "Unable to continue"
        : category === "warning"
          ? "Please review"
          : category === "success"
            ? "Success"
            : "Notice";
    setTimeout(() => showToast(title, item.textContent.trim(), category), index * 200);
  });

  const modal = $("#civic-modal");
  const modalBox = $("#civic-modal-box");
  const modalTitle = $("#modal-title");
  let lastFocus = null;
  const titles = {
    privacy: "Privacy Notice",
    help: "Help",
    charter: "Citizens Charter",
    foi: "Freedom of Information (FOI)",
    dpa: "DPA 2012 Notice",
    dict: "DICT eGov Integration",
    iso27001: "ISO/IEC 27001 Gateway",
  };

  function focusables() {
    if (!modalBox) return [];
    return $$("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])", modalBox).filter(
      (el) => !el.hasAttribute("disabled") && el.getClientRects().length > 0
    );
  }

  function openModal(name) {
    if (!modal) return;
    lastFocus = document.activeElement;
    $$("[data-modal-panel]").forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.modalPanel !== name);
    });
    if (modalTitle) modalTitle.textContent = titles[name] || "Notice";
    modal.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
    const closeBtn = $("[data-close-modal]", modal);
    (closeBtn || modalBox)?.focus?.();
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
    if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
  }

  $$("[data-open-modal]").forEach((btn) => {
    btn.addEventListener("click", () => openModal(btn.dataset.openModal));
  });
  $$("[data-close-modal]").forEach((btn) => btn.addEventListener("click", closeModal));
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeModal();
      dismissToast();
    }
    if (e.key === "Tab" && modal && !modal.classList.contains("hidden")) {
      const items = focusables();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });

  $$("[data-toggle-password]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = $(btn.dataset.togglePassword);
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", String(show));
      const icon = $("svg", btn);
      if (icon) setIcon(icon, show ? "eye-slash" : "eye", "");
    });
  });

  function setStrength(input) {
    const min = Number(input.dataset.min || 12);
    const label = $("[data-strength-label]");
    const bars = $$("[data-strength-bar]");
    const n = input.value.length;
    let score = 0;
    if (n === 0) score = 0;
    else if (n < min) score = 1;
    else if (n < min + 2) score = 2;
    else if (n < min + 4) score = 3;
    else score = 4;
    const names = ["Too Short", "Too short", "Meets minimum", "Good length", "Strong passphrase"];
    const colors = ["#E2EDE3", "#D93025", "#A07800", "#22B33A", "#12902B"];
    if (label) {
      label.textContent = names[score];
      label.style.color = score ? colors[score] : "#5F7265";
    }
    bars.forEach((bar, i) => {
      bar.style.backgroundColor = i < score ? colors[score] : "#E2EDE3";
    });
  }

  $$("[data-strength]").forEach((input) => {
    input.addEventListener("input", () => setStrength(input));
  });

  $$("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = $(btn.dataset.copy);
      if (!target) return;
      const value = target.value || target.textContent.trim();
      try {
        await navigator.clipboard.writeText(value);
        const original = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => {
          btn.textContent = original;
        }, 1600);
      } catch {
        if (target.select) target.select();
      }
    });
  });

  $$("input[type='file'][data-file-name]").forEach((input) => {
    input.addEventListener("change", () => {
      const out = $(input.dataset.fileName);
      if (out) out.textContent = input.files?.[0]?.name || "No file selected";
    });
  });

  function showFieldError(input, message) {
    if (!input) return false;
    input.classList.add("border-[#D93025]");
    input.setAttribute('aria-invalid', 'true');
    const err = input.closest("[data-field]")?.querySelector("[data-field-error]");
    if (err) {
      if (!err.id && input.id) err.id = `${input.id}-error`;
      if (err.id) {
        const descriptions = new Set((input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
        descriptions.add(err.id);
        input.setAttribute('aria-describedby', [...descriptions].join(' '));
      }
      err.textContent = message;
      err.classList.remove("hidden");
    }
    return false;
  }

  function clearFieldError(input) {
    if (!input) return;
    input.classList.remove("border-[#D93025]");
    input.removeAttribute('aria-invalid');
    const err = input.closest("[data-field]")?.querySelector("[data-field-error]");
    if (err) err.classList.add("hidden");
  }

  const loginForm = $("[data-login-form]");
  if (loginForm) {
    const identifier = $("#identifier", loginForm);
    const password = $("#password", loginForm);
    const submitBtn = $("[data-login-submit]", loginForm);
    const submitText = $("[data-login-submit-text]", loginForm);
    const roleInput = $("#login-role", loginForm);
    const roleLabel = $("#identifier-label");
    const roleHint = $("#identifier-hint");
    const roleIcon = $("#identifier-icon");
    const activeTab =
      "flex-1 py-2 px-2.5 rounded-[8px] text-center transition-all bg-[#12902B] text-white shadow-xs flex items-center justify-center gap-1.5 text-xs font-semibold focus:outline-none cursor-pointer border-0";
    const idleTab =
      "flex-1 py-2 px-2.5 rounded-[8px] text-center transition-all bg-white border border-[#E2EDE3] text-[#5F7265] hover:text-[#11291A] hover:border-[#22B33A]/40 flex items-center justify-center gap-1.5 text-xs font-semibold focus:outline-none cursor-pointer";
    const roleCopy = {
      resident: {
        labelHtml: 'Resident ID, PhilSys Card No., or Email <span class="text-[#D93025]">*</span>',
        placeholder: "Enter PhilSys ID, Citizen No., or Email",
        hint: "e.g. SCN-2025-XXXX or juan@philsys.gov.ph",
        iconName: "person",
        iconClass: "absolute left-3 text-[#5F7265] text-lg pointer-events-none",
      },
      staff: {
        labelHtml: 'Staff Employee ID or Official Gov Email <span class="text-[#D93025]">*</span>',
        placeholder: "e.g. SCN-STAFF-2026 or staff@pilalaguna.gov.ph",
        hint: "Authorized barangay clerks, health workers & registry officers",
        iconName: "person-badge",
        iconClass: "absolute left-3 text-[#5F7265] text-lg pointer-events-none",
      },
      captain: {
        labelHtml: "Executive / Official Credentials <span class=\"text-[#D93025]\">*</span>",
        placeholder: "Enter Punong Barangay executive ID or Gov.ph email",
        hint: "Restricted executive administrative access with hardware/OTP 2FA",
        iconName: "key",
        iconClass: "absolute left-3 text-[#5F7265] text-lg pointer-events-none",
      },
    };

    function selectRole(role) {
      const config = roleCopy[role];
      if (!config) return;
      if (roleInput) roleInput.value = role;
      $$("[data-role-tab]").forEach((btn) => {
        const on = btn.dataset.roleTab === role;
        btn.className = on ? activeTab : idleTab;
        btn.setAttribute("aria-selected", String(on));
        btn.tabIndex = on ? 0 : -1;
        if (on) loginForm.setAttribute("aria-labelledby", btn.id);
      });
      if (roleLabel) roleLabel.innerHTML = config.labelHtml;
      if (roleHint) roleHint.textContent = config.hint;
      if (identifier) identifier.placeholder = config.placeholder;
      if (roleIcon) setIcon(roleIcon, config.iconName, config.iconClass);
    }

    $$("[data-role-tab]").forEach((btn) => {
      btn.addEventListener("click", () => selectRole(btn.dataset.roleTab));
      btn.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const tabs = $$('[data-role-tab]');
        const index = tabs.indexOf(btn);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
          : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        selectRole(tabs[next].dataset.roleTab);
        tabs[next].focus();
      });
    });
    selectRole(roleInput?.value || 'resident');
    window.addEventListener('pageshow', () => {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('opacity-90', 'cursor-not-allowed'); }
      if (submitText) submitText.textContent = 'Sign in';
    });
    [identifier, password].forEach((input) => {
      input?.addEventListener("input", () => clearFieldError(input));
    });
    loginForm.addEventListener("submit", (e) => {
      let ok = true;
      if (!identifier?.value.trim()) {
        ok = showFieldError(identifier, "Enter your username or email.");
      }
      if (!password?.value.trim()) {
        ok = showFieldError(password, "Enter your password.") && ok;
      }
      if (!ok) {
        e.preventDefault();
        loginForm.querySelector('[aria-invalid="true"]')?.focus();
        return;
      }
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.classList.add("opacity-90", "cursor-not-allowed");
      }
      if (submitText) submitText.textContent = "Signing in…";
    });
  }

  const verifyForm = $("[data-verify-form]");
  verifyForm?.addEventListener("submit", (e) => {
    e.preventDefault();
    const value = ($("[name='document_number']", verifyForm)?.value || "").trim();
    if (!value) return;
    window.location.href = `/verify/${encodeURIComponent(value)}`;
  });

  const wizard = $("[data-register-wizard]");
  if (wizard) {
    const steps = $$("[data-step]", wizard);
    const currentLabel = $("[data-step-current]");
    const nextLabel = $("[data-step-next]");
    const bar = $("[data-step-bar]");
    const pill = $("[data-wizard-pill]");
    const titles = [
      "Step 1 of 3 — Identity",
      "Step 2 of 3 — Residency",
      "Step 3 of 3 — Security & Consent",
    ];
    const nexts = ["Next: Residency & Domicile", "Next: Security & Consent", "Pending declaration"];
    const percents = [33, 66, 90];
    let current = 0;
    const errorKeys = {
      0: ["first_name", "last_name", "birth_date"],
      1: [],
      2: ["email", "username", "password", "password_confirmation", "privacy_consent"],
    };
    const hasServerError = steps.some((step) => step.querySelector("[data-server-error]"));
    if (hasServerError) {
      const idx = steps.findIndex((step) => step.querySelector("[data-server-error]"));
      if (idx >= 0) current = idx;
    }

    function paint() {
      steps.forEach((step, i) => {
        step.classList.toggle("hidden", i !== current);
      });
      $$("[data-stepper-item]").forEach((item, i) => {
        const bubble = $("[data-stepper-bubble]", item);
        const kicker = $("[data-stepper-kicker]", item);
        item.removeAttribute("aria-current");
        if (!bubble) return;
        if (i < current) {
          bubble.className =
            "w-8 h-8 rounded-full bg-core-green text-white flex items-center justify-center font-bold text-[14px] shadow-sm shrink-0";
          bubble.innerHTML =
            '<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"></path></svg>';
          if (kicker) {
            kicker.className = "block text-[12px] font-bold uppercase tracking-wider text-core-green";
            kicker.textContent = `Step ${i + 1} • Done`;
          }
        } else if (i === current) {
          item.setAttribute("aria-current", "step");
          bubble.className =
            "w-8 h-8 rounded-full bg-card-white border-2 border-sun-yellow ring-2 ring-sun-yellow/40 flex items-center justify-center font-bold text-[14px] text-primary-dark shadow-sm shrink-0";
          bubble.textContent = String(i + 1);
          if (kicker) {
            kicker.className = "block text-[12px] font-bold uppercase tracking-wider text-primary-dark";
            kicker.textContent = `Step ${i + 1}`;
          }
        } else {
          bubble.className =
            "w-8 h-8 rounded-full border-2 border-border-ui bg-page-bg flex items-center justify-center font-semibold text-[13px] shrink-0 text-muted";
          bubble.textContent = String(i + 1);
          if (kicker) {
            kicker.className = "block text-[12px] font-bold uppercase tracking-wider";
            kicker.textContent = `Step ${i + 1}`;
          }
        }
      });
      if (currentLabel) currentLabel.textContent = `${titles[current]} — ${percents[current]}% complete`;
      if (nextLabel) nextLabel.textContent = nexts[current];
      if (bar) {
        bar.style.width = `${percents[current]}%`;
        bar.parentElement?.setAttribute("aria-valuenow", String(percents[current]));
      }
      if (pill) pill.textContent = titles[current];
    }

    function requiredOk(stepEl, focus=false) {
      if (window.civicValidation) return window.civicValidation.validateContainer(stepEl,{includeHidden:true,focus});
      let ok = true;
      $$("input, select, textarea", stepEl).forEach((input) => {
        if (input.disabled) return;
        const empty = input.type === "checkbox" ? !input.checked : !String(input.value || "").trim();
        if (empty && input.hasAttribute("data-required")) {
          showFieldError(input, input.dataset.requiredMessage || "This field is required.");
          ok = false;
        } else if (!input.checkValidity()) {
          showFieldError(input, input.validationMessage || "Please check this field.");
          ok = false;
        } else {
          clearFieldError(input);
        }
      });
      return ok;
    }

    $$("[data-next]", wizard).forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!requiredOk(steps[current],true)) return;
        if (current < steps.length - 1) {
          current += 1;
          paint();
        }
      });
    });
    $$("[data-prev]", wizard).forEach((btn) => {
      btn.addEventListener("click", () => {
        if (current > 0) {
          current -= 1;
          paint();
        }
      });
    });
    wizard.addEventListener("submit", (e) => {
      const invalidStep = steps.findIndex(step => !requiredOk(step));
      if (invalidStep >= 0) {
        current = invalidStep; paint();
        e.preventDefault();
        steps[current].querySelector("[aria-invalid=true], [data-required]")?.focus();
        return;
      }
      const btn = $("[data-register-submit]", wizard);
      if (btn) {
        btn.disabled = true;
        const label = $("[data-register-submit-text]", btn);
        if (label) label.textContent = "Submitting…";
      }
    });
    paint();
    void errorKeys;
  }
})();
