// Voice input for forms (if supported)
if ('webkitSpeechRecognition' in window) {
    const recognition = new webkitSpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'sw-TZ';

    document.querySelectorAll('[data-voice]').forEach(button => {
        button.addEventListener('click', function() {
            const targetId = this.getAttribute('data-target');
            const input = document.getElementById(targetId);
            if (!input) return;
            recognition.start();
            recognition.onresult = function(event) {
                input.value = event.results[0][0].transcript;
            };
            recognition.onerror = function(event) {
                alert('Hitilafu ya sauti: ' + event.error);
            };
        });
    });
} else {
    console.log('Voice recognition not supported');
}