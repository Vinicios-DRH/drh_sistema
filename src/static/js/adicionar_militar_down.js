document.getElementById('add_obm_funcao').addEventListener('click', function () {
    var container = document.getElementById('obm_funcao_container');
    var newGroup = container.firstElementChild.cloneNode(true);
    container.appendChild(newGroup);
});

document.getElementById('remove_obm_funcao').addEventListener('click', function () {
    var container = document.getElementById('obm_funcao_container');
    if (container.children.length > 1) {
        container.removeChild(container.lastElementChild);
    }
});
window.onload = function () {
    document.addEventListener("DOMContentLoaded", function () {
        var fileInput = document.getElementById('fileInput');

        if (fileInput) {
            fileInput.addEventListener('change', function (event) {
                var files = event.target.files;
                var filenames = [];

                for (var i = 0; i < files.length; i++) {
                    filenames.push(files[i].name);
                }

                console.log("Arquivos selecionados:", filenames); // Log para depuração

                fetch('/verificar-arquivos', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ 'filenames': filenames }),
                })
                    .then(response => response.json())
                    .then(data => {
                        console.log("Resposta do servidor:", data); // Log para depuração
                        if (data.exists.length > 0) {
                            alert('Os seguintes arquivos já existem no servidor: ' + data.exists.join(', '));
                        }
                    })
                    .catch(error => {
                        console.error("Erro ao verificar arquivos:", error);
                    });
            });
        } else {
            console.error("Elemento fileInput não encontrado.");
        }
    });
};

document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('form[method="POST"]');

    // ======= LISTA DE SELECTS OBRIGATÓRIOS (ajuste conforme sua regra) =======
    const requiredSelects = [
        { id: 'estado_civil', label: 'Estado civil' },
        { id: 'obm_ids_1', label: 'OBM principal' },
        { id: 'funcao_ids_1', label: 'Função na OBM' },
        { id: 'posto_grad_id', label: 'Posto/Graduação' },
        { id: 'quadro_id', label: 'Quadro' },
        { id: 'especialidade_id', label: 'Especialidade' },
        { id: 'sexo', label: 'Sexo' },
        { id: 'raca', label: 'Raça/Cor' },
        { id: 'localidade_id', label: 'Localidade' },
        { id: 'situacao_id', label: 'Situação' },
        { id: 'destino_id', label: 'Destino' },
        // Se quiser tornar "grau_instrucao" obrigatório: 
        // { id:'grau_instrucao',   label:'Grau de instrução' },
    ];

    const isEmpty = (v) => {
        if (v === undefined || v === null) return true;
        const s = String(v).trim();
        return s === '' || s === '0' || s.toLowerCase() === 'none';
    };

    const setInvalid = (el, msg) => {
        el.classList.add('is-invalid');
        // cria/atualiza uma invalid-feedback só do JS (não interfere nas do WTForms)
        let fb = el.parentElement.querySelector('.invalid-feedback.js');
        if (!fb) {
            fb = document.createElement('div');
            fb.className = 'invalid-feedback js';
            el.parentElement.appendChild(fb);
        }
        fb.textContent = msg || 'Campo obrigatório';
    };

    const clearInvalid = (el) => {
        el.classList.remove('is-invalid');
        const fb = el.parentElement.querySelector('.invalid-feedback.js');
        if (fb) fb.remove();
    };

    // limpa erro ao selecionar algo
    document.querySelectorAll('select').forEach(el => {
        el.addEventListener('change', () => {
            if (!isEmpty(el.value)) clearInvalid(el);
        });
    });

    // clica em itens do modal para focar o campo
    const list = document.getElementById('missingFieldsList');
    list?.addEventListener('click', (ev) => {
        const btn = ev.target.closest('button[data-target]');
        if (!btn) return;
        const target = document.querySelector(btn.getAttribute('data-target'));
        const modalEl = document.getElementById('missingFieldsModal');
        if (target && modalEl) {
            bootstrap.Modal.getInstance(modalEl)?.hide();
            setTimeout(() => {
                target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                target.focus({ preventScroll: true });
            }, 200);
        }
    });

    form?.addEventListener('submit', (e) => {
        const missing = [];
        requiredSelects.forEach(({ id, label }) => {
            const el = document.getElementById(id);
            if (!el) return;
            if (isEmpty(el.value)) {
                missing.push({ id, label, el });
                setInvalid(el, `Selecione ${label}.`);
            } else {
                clearInvalid(el);
            }
        });

        if (missing.length > 0) {
            e.preventDefault();

            // Preenche a lista no modal
            list.innerHTML = '';
            missing.forEach(({ id, label }) => {
                const li = document.createElement('li');
                li.className = 'mb-1';
                li.innerHTML = `<button type="button" class="btn btn-link p-0 text-start link-light" data-target="#${id}">
          <i class="bi bi-dot"></i> ${label}
        </button>`;
                list.appendChild(li);
            });

            // Mostra modal
            const modal = new bootstrap.Modal(document.getElementById('missingFieldsModal'));
            modal.show();

            // Rola pro primeiro faltando
            const first = missing[0].el;
            setTimeout(() => {
                first.scrollIntoView({ behavior: 'smooth', block: 'center' });
                first.focus({ preventScroll: true });
            }, 200);
        }
    });
});