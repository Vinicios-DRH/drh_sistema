document.getElementById('add_obm_funcao').addEventListener('click', function() {
    var container = document.getElementById('obm_funcao_container');
    var newGroup = container.firstElementChild.cloneNode(true);
    container.appendChild(newGroup);
});

document.getElementById('remove_obm_funcao').addEventListener('click', function() {
    var container = document.getElementById('obm_funcao_container');
    if (container.children.length > 1) {
        container.removeChild(container.lastElementChild);
    }
});
window.onload = function() {
    document.addEventListener("DOMContentLoaded", function() {
        var fileInput = document.getElementById('fileInput');

        if (fileInput) {
            fileInput.addEventListener('change', function(event) {
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