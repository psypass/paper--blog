const PaperBlogSearchMode = (() => {
  const BLOG_TYPE_VALUES = ["popular", "learning", "technical"];
  const BLOG_TYPE_STATUS = {
    popular: "版本：科普解读",
    learning: "版本：学习笔记",
    technical: "版本：技术模式已启用"
  };

  function blogTypeAt(index) {
    return BLOG_TYPE_VALUES[Number(index)] || "learning";
  }

  function createBlogTypePill(blogType, canvasRef, computed) {
    const blogTypeIndex = computed(() => Math.max(0, BLOG_TYPE_VALUES.indexOf(blogType.value)));
    const blogTypeStatus = computed(() => BLOG_TYPE_STATUS[blogType.value] || BLOG_TYPE_STATUS.learning);
    let animationFrame = 0;
    let burstTimer = 0;

    function burstParticles() {
      const canvas = canvasRef.value;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(rect.width * scale));
      canvas.height = Math.max(1, Math.round(rect.height * scale));
      const context = canvas.getContext("2d");
      if (!context) return;

      const particles = Array.from({ length: 35 }, () => {
        const angle = Math.random() * Math.PI * 2;
        const speed = 1.8 + Math.random() * 3.2;
        return {
          x: canvas.width * 0.722,
          y: canvas.height * 0.5,
          vx: Math.cos(angle) * speed * scale,
          vy: Math.sin(angle) * speed * scale,
          radius: (1.5 + Math.random() * 2) * scale,
          alpha: 0.85 + Math.random() * 0.15,
          decay: 0.018 + Math.random() * 0.018,
          color: Math.random() > 0.45 ? "103, 232, 249" : "255, 255, 255"
        };
      });

      cancelAnimationFrame(animationFrame);
      function draw() {
        context.clearRect(0, 0, canvas.width, canvas.height);
        const living = particles.filter((particle) => particle.alpha > 0.02);
        living.forEach((particle) => {
          particle.x += particle.vx;
          particle.y += particle.vy;
          particle.vx *= 0.98;
          particle.vy *= 0.98;
          particle.alpha -= particle.decay;
          context.beginPath();
          context.fillStyle = `rgba(${particle.color}, ${Math.max(0, particle.alpha)})`;
          context.shadowBlur = 9 * scale;
          context.shadowColor = `rgba(${particle.color}, ${particle.alpha})`;
          context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
          context.fill();
        });
        context.shadowBlur = 0;
        if (living.length) animationFrame = requestAnimationFrame(draw);
      }
      draw();
    }

    function selectBlogType(type) {
      if (!BLOG_TYPE_VALUES.includes(type) || blogType.value === type) return;
      blogType.value = type;
      if (type === "technical") {
        window.clearTimeout(burstTimer);
        burstTimer = window.setTimeout(burstParticles, 150);
      }
    }

    function updateBlogType(event) {
      selectBlogType(blogTypeAt(event.target.value));
    }

    return { blogTypeIndex, blogTypeStatus, selectBlogType, updateBlogType };
  }

  return { createBlogTypePill };
})();

window.PaperBlogSearchMode = PaperBlogSearchMode;
