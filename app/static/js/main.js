// Smart Attendance System - Client Scripts
document.addEventListener("DOMContentLoaded", function () {
    // Auto-dismiss standard alerts after 6 seconds
    setTimeout(function () {
        const alerts = document.querySelectorAll(".alert:not(.alert-permanent)");
        alerts.forEach(function (alert) {
            try {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            } catch (e) {}
        });
    }, 6000);
});
