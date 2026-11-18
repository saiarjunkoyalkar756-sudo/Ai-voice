(function () {
  const AUTH_TOKEN_KEY = "voicely-auth-token";
  const DASHBOARD = "/tinglish-vk-realty/dashboard";

  const loginForm = document.getElementById("login-form");
  const otpLoginForm = document.getElementById("otp-login-form");
  const forgotForm = document.getElementById("forgot-form");
  const registerForm = document.getElementById("register-form");

  const tabSignin = document.getElementById("tab-signin");
  const tabOtp = document.getElementById("tab-otp");
  const tabRegister = document.getElementById("tab-register");

  const linkForgotPw = document.getElementById("link-forgot-pw");
  const linkBackLogin = document.getElementById("link-back-login");
  const linkCancelForgot = document.getElementById("link-cancel-forgot");

  if (!loginForm) return;

  function setAuthToken(token) {
    if (token) localStorage.setItem(AUTH_TOKEN_KEY, token);
    else localStorage.removeItem(AUTH_TOKEN_KEY);
  }

  function hideAllForms() {
    loginForm.hidden = true;
    if (otpLoginForm) otpLoginForm.hidden = true;
    if (forgotForm) forgotForm.hidden = true;
    if (registerForm) registerForm.hidden = true;
  }

  function setActiveTab(tabBtn) {
    [tabSignin, tabOtp, tabRegister].forEach((t) => {
      if (t) t.classList.remove("active");
    });
    if (tabBtn) tabBtn.classList.add("active");
  }

  // Tab: Password Sign-In
  if (tabSignin) {
    tabSignin.addEventListener("click", () => {
      hideAllForms();
      loginForm.hidden = false;
      setActiveTab(tabSignin);
    });
  }

  // Tab: Email OTP Sign-In
  if (tabOtp) {
    tabOtp.addEventListener("click", () => {
      hideAllForms();
      if (otpLoginForm) otpLoginForm.hidden = false;
      setActiveTab(tabOtp);
    });
  }

  // Tab: Register
  if (tabRegister) {
    tabRegister.addEventListener("click", () => {
      hideAllForms();
      if (registerForm) registerForm.hidden = false;
      setActiveTab(tabRegister);
    });
  }

  // Forgot Password Links
  if (linkForgotPw) {
    linkForgotPw.addEventListener("click", (e) => {
      e.preventDefault();
      hideAllForms();
      if (forgotForm) forgotForm.hidden = false;
      [tabSignin, tabOtp, tabRegister].forEach((t) => {
        if (t) t.classList.remove("active");
      });
    });
  }

  function backToPasswordLogin(e) {
    if (e) e.preventDefault();
    hideAllForms();
    loginForm.hidden = false;
    setActiveTab(tabSignin);
  }

  if (linkBackLogin) linkBackLogin.addEventListener("click", backToPasswordLogin);
  if (linkCancelForgot) linkCancelForgot.addEventListener("click", backToPasswordLogin);

  // 1. Password Login Handler
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById("login-error");
    const submitBtn = document.getElementById("login-submit");
    errorEl.textContent = "";
    submitBtn.disabled = true;
    const prev = submitBtn.textContent;
    submitBtn.textContent = "Signing in…";
    const fd = new FormData(e.target);
    const email = (fd.get("email") || "").toString().trim();
    const password = (fd.get("password") || "").toString();

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Invalid email or password");
      }
      const data = await res.json();
      setAuthToken(data.access_token);
      window.location.replace(DASHBOARD);
    } catch (err) {
      errorEl.textContent = err.message || "Login failed";
      submitBtn.disabled = false;
      submitBtn.textContent = prev;
    }
  });

  // 2. Email OTP Sign-In Handlers
  const otpSendBtn = document.getElementById("otp-login-send-btn");
  const otpEmailInput = document.getElementById("otp-login-email");
  const otpStep1 = document.getElementById("otp-login-step1");
  const otpStep2 = document.getElementById("otp-login-step2");
  const otpCodeInput = document.getElementById("otp-login-code");
  const otpError = document.getElementById("otp-login-error");
  const otpResendBtn = document.getElementById("otp-login-resend-btn");

  async function requestSignInOtp() {
    const email = (otpEmailInput.value || "").trim();
    if (!email || !email.includes("@")) {
      otpError.textContent = "Please enter a valid email address.";
      return;
    }
    otpError.textContent = "";
    otpSendBtn.disabled = true;
    otpSendBtn.textContent = "Sending code…";

    try {
      const res = await fetch("/api/auth/otp-login/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to send verification code.");

      otpStep1.hidden = true;
      otpStep2.hidden = false;
      if (otpCodeInput) otpCodeInput.focus();
    } catch (err) {
      otpError.textContent = err.message || "Failed to send code.";
      otpSendBtn.disabled = false;
      otpSendBtn.textContent = "Send Sign-in Code";
    }
  }

  if (otpSendBtn) otpSendBtn.addEventListener("click", requestSignInOtp);
  if (otpResendBtn) otpResendBtn.addEventListener("click", requestSignInOtp);

  if (otpLoginForm) {
    otpLoginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = (otpEmailInput.value || "").trim();
      const otp = (otpCodeInput.value || "").trim();
      const verifyBtn = document.getElementById("otp-login-verify-btn");
      otpError.textContent = "";

      if (otp.length !== 6) {
        otpError.textContent = "Please enter the 6-digit verification code.";
        return;
      }

      verifyBtn.disabled = true;
      verifyBtn.textContent = "Verifying…";

      try {
        const res = await fetch("/api/auth/otp-login/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ email, otp }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "Verification failed.");

        setAuthToken(data.access_token);
        window.location.replace(DASHBOARD);
      } catch (err) {
        otpError.textContent = err.message || "Verification failed.";
        verifyBtn.disabled = false;
        verifyBtn.textContent = "Verify & Sign In";
      }
    });
  }

  // 3. Forgot Password Handlers
  const forgotSendBtn = document.getElementById("forgot-send-btn");
  const forgotEmailInput = document.getElementById("forgot-email");
  const forgotStep1 = document.getElementById("forgot-step1");
  const forgotStep2 = document.getElementById("forgot-step2");
  const forgotOtpInput = document.getElementById("forgot-otp");
  const forgotNewPass = document.getElementById("forgot-new-pass");
  const forgotError = document.getElementById("forgot-error");
  const forgotSuccess = document.getElementById("forgot-success");
  const forgotResendBtn = document.getElementById("forgot-resend-btn");

  async function requestForgotOtp() {
    const email = (forgotEmailInput.value || "").trim();
    if (!email || !email.includes("@")) {
      forgotError.textContent = "Please enter a valid email address.";
      return;
    }
    forgotError.textContent = "";
    forgotSendBtn.disabled = true;
    forgotSendBtn.textContent = "Sending code…";

    try {
      const res = await fetch("/api/auth/forgot-password/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to send reset code.");

      forgotStep1.hidden = true;
      forgotStep2.hidden = false;
      if (forgotOtpInput) forgotOtpInput.focus();
    } catch (err) {
      forgotError.textContent = err.message || "Failed to send code.";
      forgotSendBtn.disabled = false;
      forgotSendBtn.textContent = "Send Reset Code";
    }
  }

  if (forgotSendBtn) forgotSendBtn.addEventListener("click", requestForgotOtp);
  if (forgotResendBtn) forgotResendBtn.addEventListener("click", requestForgotOtp);

  if (forgotForm) {
    forgotForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = (forgotEmailInput.value || "").trim();
      const otp = (forgotOtpInput.value || "").trim();
      const new_password = (forgotNewPass.value || "").trim();
      const resetBtn = document.getElementById("forgot-reset-btn");
      forgotError.textContent = "";

      if (otp.length !== 6) {
        forgotError.textContent = "Please enter the 6-digit verification code.";
        return;
      }
      if (new_password.length < 8) {
        forgotError.textContent = "Password must be at least 8 characters.";
        return;
      }

      resetBtn.disabled = true;
      resetBtn.textContent = "Updating password…";

      try {
        const res = await fetch("/api/auth/forgot-password/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, otp, new_password }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "Failed to reset password.");

        forgotStep2.hidden = true;
        forgotSuccess.hidden = false;
        forgotSuccess.textContent = "Password updated successfully! Logging you in…";

        // Auto sign-in with newly set password
        const loginRes = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ email, password: new_password }),
        });
        if (loginRes.ok) {
          const loginData = await loginRes.json();
          setAuthToken(loginData.access_token);
          setTimeout(() => window.location.replace(DASHBOARD), 800);
        } else {
          setTimeout(backToPasswordLogin, 1500);
        }
      } catch (err) {
        forgotError.textContent = err.message || "Reset failed.";
        resetBtn.disabled = false;
        resetBtn.textContent = "Reset Password & Sign In";
      }
    });
  }

  // 4. Registration Handler
  if (registerForm) {
    registerForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorEl = document.getElementById("register-error");
      const submitBtn = document.getElementById("register-submit");
      errorEl.textContent = "";
      submitBtn.disabled = true;
      const prev = submitBtn.textContent;
      submitBtn.textContent = "Creating account…";

      const fd = new FormData(e.target);
      const email = (fd.get("email") || "").toString().trim();
      const password = (fd.get("password") || "").toString();
      const org_name = (fd.get("org_name") || "Voicely").toString().trim();

      try {
        const res = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ email, password, org_name }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Registration failed");
        }
        const data = await res.json();
        setAuthToken(data.access_token);
        window.location.replace(DASHBOARD);
      } catch (err) {
        errorEl.textContent = err.message || "Registration failed";
        submitBtn.disabled = false;
        submitBtn.textContent = prev;
      }
    });
  }

  async function verifyExistingSession() {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (!token) return false;
    try {
      const res = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  verifyExistingSession().then((ok) => {
    if (ok) window.location.replace(DASHBOARD);
  });
})();
