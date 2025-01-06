document.getElementById('btn-editar').onclick = function() {
    document.getElementById('form-editar').style.display = 'block';
    this.style.display = 'none'; // Oculta o botão de editar
    document.getElementById('btn-excluir').style.display = 'none'; // Oculta o botão de excluir
};

// Script para exibir os botões quando o formulário for fechado (por exemplo, ao clicar fora do formulário ou ao salvar as alterações)
function mostrarBotoes() {
    document.getElementById('form-editar').style.display = 'none';
    document.getElementById('btn-editar').style.display = 'inline-block'; // Exibe o botão de editar
    document.getElementById('btn-excluir').style.display = 'inline-block'; // Exibe o botão de excluir
}