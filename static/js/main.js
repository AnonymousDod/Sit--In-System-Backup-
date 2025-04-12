// Mobile menu toggle
document.addEventListener('DOMContentLoaded', function() {
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    const navMenu = document.querySelector('.nav-menu');

    if (mobileMenuBtn && navMenu) {
        mobileMenuBtn.addEventListener('click', function() {
            navMenu.classList.toggle('active');
        });
    }

    // Flash messages
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        const closeBtn = message.querySelector('.flash-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                message.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => {
                    message.remove();
                }, 300);
            });
        }
    });

    // Loading overlay
    const loadingOverlay = document.querySelector('.loading-overlay');
    if (loadingOverlay) {
        window.showLoading = function() {
            loadingOverlay.style.display = 'flex';
        };

        window.hideLoading = function() {
            loadingOverlay.style.display = 'none';
        };
    }

    // Form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;

            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add('error');
                } else {
                    field.classList.remove('error');
                }
            });

            if (!isValid) {
                e.preventDefault();
                alert('Please fill in all required fields');
            }
        });
    });

    // Time input validation
    const timeInputs = document.querySelectorAll('input[type="time"]');
    timeInputs.forEach(input => {
        input.addEventListener('change', function() {
            const time = this.value;
            if (time) {
                const [hours, minutes] = time.split(':');
                const date = new Date();
                date.setHours(parseInt(hours));
                date.setMinutes(parseInt(minutes));

                const minTime = new Date();
                minTime.setHours(8, 0, 0); // 8:00 AM

                const maxTime = new Date();
                maxTime.setHours(17, 0, 0); // 5:00 PM

                if (date < minTime || date > maxTime) {
                    this.value = '';
                    alert('Please select a time between 8:00 AM and 5:00 PM');
                }
            }
        });
    });

    // Date input validation
    const dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach(input => {
        input.addEventListener('change', function() {
            const selectedDate = new Date(this.value);
            const today = new Date();
            today.setHours(0, 0, 0, 0);

            if (selectedDate < today) {
                this.value = '';
                alert('Please select a future date');
            }
        });
    });

    // AJAX form submissions
    const ajaxForms = document.querySelectorAll('form[data-ajax="true"]');
    ajaxForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            const url = this.getAttribute('action');
            const method = this.getAttribute('method') || 'POST';

            showLoading();

            fetch(url, {
                method: method,
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                hideLoading();
                if (data.success) {
                    if (data.redirect) {
                        window.location.href = data.redirect;
                    } else {
                        showFlashMessage('success', data.message);
                    }
                } else {
                    showFlashMessage('error', data.message);
                }
            })
            .catch(error => {
                hideLoading();
                showFlashMessage('error', 'An error occurred. Please try again.');
                console.error('Error:', error);
            });
        });
    });
});

// Flash message helper
function showFlashMessage(type, message) {
    const flashContainer = document.querySelector('.flash-messages');
    if (!flashContainer) return;

    const flashMessage = document.createElement('div');
    flashMessage.className = `flash-message ${type}`;
    flashMessage.innerHTML = `
        <span>${message}</span>
        <button class="flash-close">&times;</button>
    `;

    flashContainer.appendChild(flashMessage);

    const closeBtn = flashMessage.querySelector('.flash-close');
    closeBtn.addEventListener('click', function() {
        flashMessage.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            flashMessage.remove();
        }, 300);
    });

    setTimeout(() => {
        flashMessage.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            flashMessage.remove();
        }, 300);
    }, 5000);
}

// Add slideOut animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style); 