async function carregarMilitares(page = 1, search = '') {
    try {
        const response = await fetch(`/api/militares?page=${page}&search=${encodeURIComponent(search)}`);
        const data = await response.json();

        const tabela = $('#example').DataTable();
        tabela.clear();

        data.militares.forEach(militar => {
            tabela.row.add([
                `<a href="/exibir-militar/${militar.id}">${militar.nome_completo}</a>`,
                militar.nome_guerra,
//                militar.especialidade,
                militar.cpf,
                militar.rg,
                militar.matricula,
//                militar.posto_grad_sigla,
                militar.obms[0] || '',
                militar.funcoes[0] || '',
                militar.obms[1] || '',
                militar.funcoes[1] || '',
                militar.quadro,
                militar.localidade,
//                militar.situacao,
//                militar.agregacoes,
                militar.destino
            ]);
        });

        tabela.draw();

        // Atualiza a paginação fora da tabela
        const paginacao = document.querySelector(".pagination");
        paginacao.innerHTML = `
            <li class="page-item ${data.has_prev ? '' : 'disabled'}">
                <a class="page-link" href="#" onclick="carregarMilitares(${data.prev_page}, '${search}')">Anterior</a>
            </li>
            <li class="page-item ${data.has_next ? '' : 'disabled'}">
                <a class="page-link" href="#" onclick="carregarMilitares(${data.next_page}, '${search}')">Próxima</a>
            </li>
        `;
    } catch (error) {
        console.error("Erro ao carregar os militares:", error);
    }
}

$(document).ready(function() {
    const tabela = $('#example').DataTable({
        paging: false,            // Desativa a paginação interna
        searching: false,         // Desativa a busca interna
        info: true,
        lengthChange: false,      // Remove a opção de alterar o número de linhas por página
        pageLength: 10,           // Número de linhas por página
        responsive: true,
        language: {
            decimal: ",",
            thousands: ".",
            sProcessing: "Processando...",
            sLengthMenu: "Mostrar _MENU_ registros",
            sZeroRecords: "Nenhum militar encontrado",
            sEmptyTable: "Nenhum dado disponível na tabela",
            sInfo: "Mostrando de _START_ até _END_ de _TOTAL_ registros",
            sInfoEmpty: "Mostrando 0 até 0 de 0 registros",
            sInfoFiltered: "(filtrado de _MAX_ registros no total)",
            sLoadingRecords: "Carregando...",
            oPaginate: {
                sFirst: "Primeiro",
                sLast: "Último",
                sNext: "Próximo",
                sPrevious: "Anterior"
            }
        }
    });

    $('#search-input').on('input', function() {
        const searchValue = this.value.trim();
        carregarMilitares(1, searchValue);
    });

    // Carrega a primeira página de militares
    carregarMilitares();
});
