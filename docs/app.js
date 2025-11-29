AOS.init({
    duration: 800,
    once: true,
    offset: 50
});

const navToggle = document.querySelector('.nav-toggle');
const navLinks = document.querySelector('.nav-links');
const nav = document.querySelector('nav');

if (navToggle) {
    navToggle.addEventListener('click', () => {
        navLinks.classList.toggle('nav-open');
        navToggle.classList.toggle('nav-open');
        
        if (navLinks.classList.contains('nav-open')) {
            navToggle.setAttribute('aria-label', 'Cerrar menú');
        } else {
            navToggle.setAttribute('aria-label', 'Abrir menú');
        }
    });
}

if (nav) {
    window.addEventListener('scroll', () => {
        if (window.scrollY > 10) {
            nav.classList.add('scrolled');
        } else {
            nav.classList.remove('scrolled');
        }
    });
}

document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
        
        if (navLinks && navLinks.classList.contains('nav-open')) {
            navLinks.classList.remove('nav-open');
            navToggle.classList.remove('nav-open');
            navToggle.setAttribute('aria-label', 'Abrir menú');
        }
    });
});



let konamiCode = [];
const pattern = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];

window.addEventListener('keydown', (e) => {
    konamiCode.push(e.key);
    konamiCode = konamiCode.slice(-pattern.length);
    
    if (konamiCode.join(',') === pattern.join(',')) {
        document.body.style.animation = 'rainbow 2s infinite';
        setTimeout(() => {
            document.body.style.animation = '';
        }, 5000);
    }
});

const style = document.createElement('style');
style.textContent = `
    @keyframes rainbow {
        0% { filter: hue-rotate(0deg); }
        100% { filter: hue-rotate(360deg); }
    }
`;
document.head.appendChild(style);


const translations = {
    es: {
        metaDescription: "Compa es un asistente de voz impulsado por IA que apoya a personas con Alzheimer y problemas de memoria. Conexión familiar 24/7 con gestión de memoria inteligente.",
        metaKeywords: "Alzheimer, asistente IA, cuidado de personas mayores, memoria, salud mental, tecnología para mayores, voz IA, Telegram",
        
        navBeneficios: "Beneficios",
        navCaracteristicas: "Características",
        navTestimonios: "Testimonios",
        navContacto: "Contacto",
        btnPH: "Upvota en PH",
        
        heroTitle: "Cuidado Conectado para Tus Seres Queridos",
        heroSubtitle: "Asistente de voz impulsado por IA que apoya a personas con Alzheimer y problemas de memoria, manteniendo a las familias unidas.",
        btnProbar: "Probar Ahora",
        btnVerMas: "Ver Más",
        heroDemoTitle: "Conversación Natural",
        heroDemoSubtitle: "Interacción por voz simple e intuitiva",

        paraQuienTitle: "¿Para Quién es Compa?",
        paraQuienSubtitle: "Diseñado para familias que enfrentan desafíos de memoria",
        persona1Title: "Familiares Cuidadores",
        persona1Text: "Mantente conectado y apoya a tus seres queridos a distancia. Recibe actualizaciones y comunícate fácilmente a través de Telegram.",
        persona2Title: "Personas con Pérdidas de Memoria",
        persona2Text: "Asistente de voz compasivo que ayuda a recordar momentos importantes y proporciona compañía constante.",
        persona3Title: "Profesionales de la Salud",
        persona3Text: "Herramienta de apoyo para mejorar la calidad de vida de pacientes con deterioro cognitivo.",

        beneficiosTitle: "Beneficios Clave",
        beneficiosSubtitle: "Cómo Compa transforma el cuidado de memoria",
        beneficio1Title: "Gestión de Memoria",
        beneficio1Text: "Sistema inteligente que almacena y recuerda momentos personales importantes cuando son necesarios.",
        beneficio2Title: "Comunicación Familiar",
        beneficio2Text: "Conexión directa con familiares a través de Telegram para mantener el vínculo familiar fuerte.",
        beneficio3Title: "Disponibilidad 24/7",
        beneficio3Text: "Compañía constante y asistencia en cualquier momento del día o la noche.",
        beneficio4Title: "Seguro y Privado",
        beneficio4Text: "Datos protegidos con encriptación y gestión segura de dispositivos.",
        beneficio5Title: "Fácil de Usar",
        beneficio5Text: "Interfaz simple con interacción por voz, sin necesidad de conocimientos técnicos.",

        caracteristicasTitle: "Características Principales",
        caracteristicasSubtitle: "Tecnología avanzada al servicio del cuidado humano",
        feature1Title: "Interacción por Voz",
        feature1Text: "Conversación natural usando Web Speech API para una experiencia intuitiva.",
        feature2Title: "IA de Google Gemini",
        feature2Text: "Respuestas inteligentes y contextuales impulsadas por tecnología de última generación.",
        feature3Title: "Bot de Telegram",
        feature3Text: "Comunicación directa entre familiares y el asistente a través de mensajería.",
        feature4Title: "Actualizaciones en Tiempo Real",
        feature4Text: "WebSocket para comunicación instantánea y sincronización de datos.",
        feature7Title: "Autenticación Segura",
        feature7Text: "Acceso protegido para garantizar la privacidad de los usuarios y datos sensibles.",
        feature8Title: "Métricas de Uso",
        feature8Text: "Información anónima para mejorar el servicio y entender patrones de interacción.",
        feature5Title: "Base de Datos Robusta",
        feature5Text: "PostgreSQL con SQLAlchemy para almacenamiento seguro y confiable.",
        feature6Title: "Multi-Dispositivo",
        feature6Text: "Soporte para múltiples dispositivos con códigos de conexión seguros.",

        /* 
          
          Las reseñas son ficticias y se añadirán testimonios reales más adelante.
        
        
        testimoniosTitle: "Lo Que Dicen Nuestros Usuarios",
        testimoniosSubtitle: "Historias reales de familias que usan Compa",
        testimonio1Text: "\"Compa ha sido un salvavidas para nuestra familia. Mi madre puede hablar con él cuando se siente sola, y yo recibo actualizaciones constantes sobre cómo está.\"",
        testimonio1Autor: "María Rodríguez",
        testimonio1Rol: "Hija de usuario con Alzheimer",
        testimonio2Text: "\"Como cuidador profesional, Compa me ayuda a proporcionar mejor atención. La gestión de memoria y las alertas familiares son increíbles.\"",
        testimonio2Autor: "Juan García",
        testimonio2Rol: "Enfermero geriátrico",
        testimonio3Text: "\"Me encanta poder hablar con Compa cuando mi familia no está. Me ayuda a recordar cosas importantes y me hace sentir acompañada.\"",
        testimonio3Autor: "Ana Martínez",
        testimonio3Rol: "Usuaria de Compa, 72 años",
        */

        ctaTitle: "Comienza a Cuidar Mejor Hoy",
        ctaSubtitle: "Únete a cientos de familias que ya confían en Compa",
        ctaBtnProbar: "Probar Compa Ahora",
        ctaBtnVotar: "Votar en Product Hunt",
        ctaBtnDonar: "Apoyar el Proyecto",

        contactoTitle: "Contáctanos",
        contactoSubtitle: "¿Tienes preguntas o sugerencias? Nos encantaría escucharte",
        formNombre: "Nombre",
        formEmail: "Email",
        formMensaje: "Mensaje / Sugerencias",
        formBtnEnviar: "Enviar Mensaje",

        footerResumen: "Asistente de voz con IA para cuidado de personas con problemas de memoria.",
        footerHechoCon: "Hecho con ❤️.",
        footerEnlaces: "Enlaces Rápidos",
        footerRecursos: "Recursos",
        footerRepo: "GitHub Repository",
        footerApp: "Aplicación Web",
        footerBot: "Bot de Telegram",
        footerContacto: "Contacto",
        footerEmail: "compamessages@gmail.com",
        footerFormulario: "Formulario de Contacto",
        footerCopyright: "&copy; 2025 Oscar Garcia (ogarmar). Algunos derechos reservados bajo <a href='https://github.com/ogarmar/Compa/blob/main/LICENSE.md'>licencia</a>.",
        heroDemoTitle: "Conversación Natural",
        heroDemoSubtitle: "Haz clic para ver la demo",
        
        // NUEVAS CLAVES SECCIÓN CÓMO USARLO
        howToUseTitle: "¿Cómo funciona Compa?",
        howToUseSubtitle: "Empezar es muy sencillo, mira este breve tutorial",
        step1Title: "Inicia Sesión",
        step1Text: "Accede de forma segura con tu número de teléfono y el código de verificación.",
        step2Title: "Conecta Telegram",
        step2Text: "Vincula el bot de Telegram para recibir mensajes de tus familiares.",
        step3Title: "Empieza a Hablar",
        step3Text: "Simplemente pulsa el micrófono y habla. Él recordará lo importante."
    },
    en: {
        metaDescription: "Compa is an AI-powered voice assistant that supports people with Alzheimer's and memory issues. 24/7 family connection with smart memory management.",
        metaKeywords: "Alzheimer's, AI assistant, elderly care, memory, mental health, senior tech, AI voice, Telegram",

        navBeneficios: "Benefits",
        navCaracteristicas: "Features",
        navTestimonios: "Testimonials",
        navContacto: "Contact",
        btnPH: "Upvote on PH",
        
        heroTitle: "Connected Care for Your Loved Ones",
        heroSubtitle: "AI-powered voice assistant that supports people with Alzheimer's and memory issues, keeping families together.",
        btnProbar: "Try Now",
        btnVerMas: "Learn More",
        heroDemoTitle: "Natural Conversation",
        heroDemoSubtitle: "Simple and intuitive voice interaction",

        paraQuienTitle: "Who is Compa For?",
        paraQuienSubtitle: "Designed for families facing memory challenges",
        persona1Title: "Family Caregivers",
        persona1Text: "Stay connected and support your loved ones remotely. Get updates and communicate easily via Telegram.",
        persona2Title: "People with Memory Loss",
        persona2Text: "A compassionate voice assistant that helps recall important moments and provides constant companionship.",
        persona3Title: "Health Professionals",
        persona3Text: "A support tool to improve the quality of life for patients with cognitive decline.",

        beneficiosTitle: "Key Benefits",
        beneficiosSubtitle: "How Compa transforms memory care",
        beneficio1Title: "Memory Management",
        beneficio1Text: "Intelligent system that stores and recalls important personal moments when needed.",
        beneficio2Title: "Family Communication",
        beneficio2Text: "Direct connection with family members via Telegram to keep the family bond strong.",
        beneficio3Title: "24/7 Availability",
        beneficio3Text: "Constant companionship and assistance at any time of the day or night.",
        beneficio4Title: "Secure and Private",
        beneficio4Text: "Data protected with encryption and secure device management.",
        beneficio5Title: "Easy to Use",
        beneficio5Text: "Simple interface with voice interaction, no technical knowledge required.",

        caracteristicasTitle: "Main Features",
        caracteristicasSubtitle: "Advanced technology at the service of human care",
        feature1Title: "Voice Interaction",
        feature1Text: "Natural conversation using the Web Speech API for an intuitive experience.",
        feature2Title: "Google Gemini AI",
        feature2Text: "Intelligent, contextual responses powered by next-generation technology.",
        feature3Title: "Telegram Bot",
        feature3Text: "Direct communication between family members and the assistant via messaging.",
        feature4Title: "Real-Time Updates",
        feature4Text: "WebSocket for instant communication and data synchronization.",
        feature7Title: "Secure Authentication",
        feature7Text: "Protected access to ensure user privacy and sensitive data.",
        feature8Title: "Usage Metrics",
        feature8Text: "Anonymous information to improve service and understand interaction patterns.",
        feature5Title: "Robust Database",
        feature5Text: "PostgreSQL with SQLAlchemy for secure and reliable storage.",
        feature6Title: "Multi-Device",
        feature6Text: "Support for multiple devices with secure connection codes.",
        
        /* 
          Las reseñas son ficticias y se añadirán testimonios reales más adelante.
        
        
        testimoniosTitle: "What Our Users Say",
        testimoniosSubtitle: "Real stories from families using Compa",
        testimonio1Text: "\"Compa has been a lifesaver for our family. My mother can talk to it when she feels lonely, and I get constant updates on how she's doing.\"",
        testimonio1Autor: "Maria Rodriguez",
        testimonio1Rol: "Daughter of user with Alzheimer's",
        testimonio2Text: "\"As a professional caregiver, Compa helps me provide better care. The memory management and family alerts are incredible.\"",
        testimonio2Autor: "John Garcia",
        testimonio2Rol: "Geriatric Nurse",
        testimonio3Text: "\"I love being able to talk to Compa when my family isn't around. It helps me remember important things and makes me feel accompanied.\"",
        testimonio3Autor: "Ana Martinez",
        testimonio3Rol: "Compa User, 72 years old",
        */

        ctaTitle: "Start Caring Better Today",
        ctaSubtitle: "Join hundreds of families who already trust Compa",
        ctaBtnProbar: "Try Compa Now",
        ctaBtnVotar: "Vote on Product Hunt",
        ctaBtnDonar: "Support the Project",

        contactoTitle: "Contact Us",
        contactoSubtitle: "Have questions or suggestions? We'd love to hear from you",
        formNombre: "Name",
        formEmail: "Email",
        formMensaje: "Message / Suggestions",
        formBtnEnviar: "Send Message",

        footerResumen: "AI voice assistant for the care of people with memory problems.",
        footerHechoCon: "Made with ❤️.",
        footerEnlaces: "Quick Links",
        footerRecursos: "Resources",
        footerRepo: "GitHub Repository",
        footerApp: "Web Application",
        footerBot: "Telegram Bot",
        footerContacto: "Contact",
        footerEmail: "compamessages@gmail.com",
        footerFormulario: "Contact Form",
        footerCopyright: "&copy; 2025 Oscar Garcia (ogarmar). Some rights reserved under <a href='https://github.com/ogarmar/Compa/blob/main/LICENSE.md'>license</a>.",
        heroDemoTitle: "Natural Conversation",
        heroDemoSubtitle: "Click to watch the demo",

        // NUEVAS CLAVES SECCIÓN CÓMO USARLO
        howToUseTitle: "How does Compa work?",
        howToUseSubtitle: "Getting started is easy, watch this short tutorial",
        step1Title: "Login",
        step1Text: "Securely access with your phone number and verification code.",
        step2Title: "Connect Telegram",
        step2Text: "Link the Telegram bot to verify messages from your family instantly.",
        step3Title: "Start Talking",
        step3Text: "Just press the microphone and talk. He will remember what matters."
    }
};

function setLanguage(lang) {
    document.documentElement.lang = lang;
    
    const translateBtn = document.getElementById('translate-btn');
    if (translateBtn) {
        translateBtn.textContent = (lang === 'es') ? 'EN' : 'ES';
    }

    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) {
        metaDesc.content = translations[lang].metaDescription;
    }
    const metaKeywords = document.querySelector('meta[name="keywords"]');
    if (metaKeywords) {
        metaKeywords.content = translations[lang].metaKeywords;
    }

    document.querySelectorAll('[data-key]').forEach(element => {
        const key = element.dataset.key;
        const translation = translations[lang][key];
        if (translation) {
            if (key === 'footerCopyright') {
                element.innerHTML = translation;
            } else {
                element.textContent = translation;
            }
        }
    });
}

function toggleLanguage() {
    const currentLang = document.documentElement.lang || 'es';
    const newLang = (currentLang === 'es') ? 'en' : 'es';
    
    setLanguage(newLang);
    
    try {
        localStorage.setItem('compa-lang', newLang);
    } catch (e) {
        console.error("No se pudo guardar el idioma en localStorage.", e);
    }
}
const form = document.getElementById('contact-form');

async function handleSubmit(event) {
  event.preventDefault();
  const submitBtn = form.querySelector('.submit-btn');
  const originalBtnHTML = submitBtn.innerHTML;
  const data = new FormData(event.target);

  submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
  submitBtn.disabled = true;

  try {
    const response = await fetch(form.action, {
      method: form.method,
      body: data,
      headers: {
        'Accept': 'application/json'
      }
    });

    if (response.ok) {
      submitBtn.innerHTML = '<i class="fas fa-check"></i> ¡Enviado!';
      form.reset();
    } else {
      submitBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
      alert('Hubo un error al enviar el mensaje. Inténtalo de nuevo.');
    }
  } catch (error) {
    console.error('Error:', error);
    submitBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
    alert('Error de red. No se pudo enviar.');
  } finally {
    setTimeout(() => {
      submitBtn.innerHTML = originalBtnHTML;
      submitBtn.disabled = false;
    }, 3000);
  }
}

if (form) {
  form.addEventListener("submit", handleSubmit);
}

document.addEventListener('DOMContentLoaded', () => {
    const contactSection = document.querySelector('.contact'); 
    const contactForm = document.querySelector('.contact-form');
    
    if (contactSection && contactForm) {
        contactSection.addEventListener('mousemove', (e) => {
            const rect = contactSection.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const width = rect.width;
            const height = rect.height;
            
            const rotateX = (y - height / 2) / height * -5; 
            const rotateY = (x - width / 2) / width * 10;
            
            contactForm.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.02)`;
            contactForm.style.transition = 'transform 0.1s ease-out';
        });
    
        contactSection.addEventListener('mouseleave', () => {
            contactForm.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale(1)';
            contactForm.style.transition = 'transform 0.5s cubic-bezier(0.25, 0.8, 0.25, 1)'; 
        });
    }

    const translateBtn = document.getElementById('translate-btn');
    if (translateBtn) {
        translateBtn.addEventListener('click', toggleLanguage);
    }

    let savedLang = 'es';
    try {
        savedLang = localStorage.getItem('compa-lang') || 'es';
    } catch (e) {
        console.warn("No se pudo leer localStorage, usando 'es'.", e);
    }
    
    setLanguage(savedLang);

    const visual = document.querySelector('.hero-visual');
    const card = document.querySelector('.demo-placeholder');
    // ... código existente ...

    // --- LÓGICA VIDEO HERO ---
    const heroCard = document.querySelector('.demo-placeholder');

    if (heroCard) {
        heroCard.addEventListener('click', function(e) {
            e.stopPropagation();
            // Si ya está activo, no hacemos nada
            if (this.classList.contains('video-active')) return;

            this.classList.add('video-active');
            
            // CAMBIO: Usamos etiqueta <video> local en vez de YouTube
            this.innerHTML = `
                <video 
                    width="100%" 
                    height="100%" 
                    autoplay
                    controls
                    style="border-radius: 20px; width: 100%; height: 100%; object-fit: cover;">
                    <source src="assets/demo.mp4" type="video/mp4">
                    Tu navegador no soporta videos HTML5.
                </video>
            `;
            
            // Quitamos la transformación 3D para facilitar el uso de los controles
            this.style.transform = 'none';
        });
    }
    if (visual && card) {
        visual.addEventListener('mousemove', (e) => {
            const rect = visual.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const width = rect.width;
            const height = rect.height;
            
            const rotateX = (y - height / 2) / height * -10;
            const rotateY = (x - width / 2) / width * 20;
            
            card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.05)`;
            card.style.transition = 'transform 0.1s ease-out';
        });

        visual.addEventListener('mouseleave', () => {
            card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale(1)';
            card.style.transition = 'transform 0.5s cubic-bezier(0.25, 0.8, 0.25, 1)'; 
        });
    }
});