// BoachieEdu JavaScript Logic - Mobile Friendly
document.addEventListener('DOMContentLoaded', () => {
  // 1. Mobile Menu Drawer Toggle
  const mobileMenuBtn = document.getElementById('mobileMenuBtn');
  const mobileMenuDrawer = document.getElementById('mobileMenuDrawer');

  if (mobileMenuBtn && mobileMenuDrawer) {
    mobileMenuBtn.addEventListener('click', () => {
      mobileMenuDrawer.classList.toggle('show');
    });
  }

  // 2. Student Level Select Handler ("Other" level input toggle)
  const levelSelect = document.getElementById('student_level');
  const levelOtherGroup = document.getElementById('level_other_group');
  const levelOtherInput = document.getElementById('level_other');

  if (levelSelect && levelOtherGroup) {
    const checkLevelOther = () => {
      if (levelSelect.value === 'Other') {
        levelOtherGroup.style.display = 'block';
        if (levelOtherInput) levelOtherInput.required = true;
      } else {
        levelOtherGroup.style.display = 'none';
        if (levelOtherInput) levelOtherInput.required = false;
      }
    };
    levelSelect.addEventListener('change', checkLevelOther);
    checkLevelOther();
  }

  // 3. Password Min-Length Validator (8 characters minimum)
  const passwordInput = document.getElementById('password');
  const passwordError = document.getElementById('password_error');

  if (passwordInput && passwordError) {
    passwordInput.addEventListener('input', () => {
      const len = passwordInput.value.length;
      if (len > 0 && len < 8) {
        passwordError.textContent = `Password must be at least 8 characters (${len}/8)`;
        passwordError.style.color = 'var(--color-danger)';
        passwordInput.style.borderColor = 'var(--color-danger)';
      } else if (len >= 8) {
        passwordError.textContent = 'Password length criteria met ✓';
        passwordError.style.color = 'var(--color-success)';
        passwordInput.style.borderColor = 'var(--color-success)';
      } else {
        passwordError.textContent = 'Must be at least 8 characters long';
        passwordError.style.color = 'var(--color-text-muted)';
        passwordInput.style.borderColor = 'var(--color-border)';
      }
    });
  }
});
