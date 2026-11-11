(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  $$("[data-toggle-password]").forEach((b) =>
    b.addEventListener("click", () => {
      const i = $(b.dataset.togglePassword);
      if (!i) return;
      i.type = i.type === "password" ? "text" : "password";
      b.setAttribute("aria-pressed", String(i.type === "text"));
    })
  );

  $$("[data-strength]").forEach((inp) => {
    const min = +inp.dataset.min || 12;
    const out = $("[data-strength-out]", inp.closest("form") || document);
    const labels = ["Too short", "Meets minimum", "Good", "Strong passphrase"];
    inp.addEventListener("input", () => {
      const n = inp.value.length;
      const score = n === 0 ? -1 : n < min ? 0 : n < min + 2 ? 1 : n < min + 4 ? 2 : 3;
      if (out) out.textContent = score < 0 ? "" : `${labels[score]} (${n}/${min}+)`;
    });
  });

  document.addEventListener("submit", (e) => {
    const f = e.target.closest("[data-confirm]");
    if (!f || f.dataset.confirmed) return;
    e.preventDefault();
    const go = () => {
      f.dataset.confirmed = "1";
      f.requestSubmit ? f.requestSubmit() : f.submit();
    };
    const m = $("#confirmModal");
    if (!m || !window.bootstrap) {
      if (confirm(f.dataset.confirm)) go();
      return;
    }
    $("#confirmModalText", m).textContent = f.dataset.confirm;
    const modal = bootstrap.Modal.getOrCreateInstance(m);
    $("#confirmModalOk", m).onclick = () => {
      modal.hide();
      go();
    };
    modal.show();
  });

  $$("[data-copy]").forEach((b) =>
    b.addEventListener("click", async () => {
      const t = $(b.dataset.copy);
      if (!t) return;
      try {
        await navigator.clipboard.writeText(t.value || t.textContent.trim());
        b.textContent = "Copied · Nakopya";
      } catch {
        t.select && t.select();
      }
    })
  );

  const fmt = (iso, mode) => {
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
    if (isNaN(d)) return null;
    const o = mode === "date" ? { dateStyle: "medium" } : { dateStyle: "medium", timeStyle: "short" };
    return new Intl.DateTimeFormat("en-PH", { ...o, timeZone: "Asia/Manila" }).format(d);
  };
  $$("time[data-fmt]").forEach((t) => {
    const s = fmt(t.dateTime, t.dataset.fmt);
    if (s) t.textContent = s;
  });

  const wizard = $("[data-register-wizard]");
  if (wizard) {
    const steps = $$("[data-step]", wizard);
    const dots = $$(".stepper .step", wizard);
    let current = 0;
    const show = (index) => {
      current = index;
      steps.forEach((step, i) => {
        step.hidden = i !== index;
      });
      dots.forEach((dot, i) => {
        dot.classList.toggle("is-active", i === index);
        dot.classList.toggle("is-done", i < index);
      });
    };
    wizard.addEventListener("click", (e) => {
      if (e.target.closest("[data-next]")) {
        e.preventDefault();
        show(Math.min(current + 1, steps.length - 1));
      }
      if (e.target.closest("[data-prev]")) {
        e.preventDefault();
        show(Math.max(current - 1, 0));
      }
    });
    show(wizard.querySelector(".is-invalid") ? steps.length - 1 : 0);
  }

  $$("input[type=file][data-preview]").forEach((input) => {
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      const out = $(input.dataset.preview);
      const err = $(input.dataset.error || "");
      if (err) err.textContent = "";
      if (!file) return;
      const max = +(input.dataset.maxBytes || 5242880);
      if (file.size > max) {
        if (err) err.textContent = `File is larger than ${(max / 1048576).toFixed(0)} MB.`;
        input.value = "";
        return;
      }
      if (out && file.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = () => {
          out.src = reader.result;
          out.hidden = false;
        };
        reader.readAsDataURL(file);
      }
    });
  });
})();
