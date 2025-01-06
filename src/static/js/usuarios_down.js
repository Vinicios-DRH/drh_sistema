$(document).ready(function() {
    $('#example').DataTable({
        "paging": true,
        "searching": true,
        "info": true,
        "lengthChange": false,  // Remover a opção de alterar o número de linhas por página
        "pageLength": 10,       // Número de linhas por página
        "language": {
            "decimal": ",",
            "thousands": ".",
            "sProcessing": "Processando...",
            "sLengthMenu": "Mostrar _MENU_ registros",
            "sZeroRecords": "Nenhum militar encontrado",
            "sEmptyTable": "Nenhum dado disponível na tabela",
            "sInfo": "Mostrando de _START_ até _END_ de _TOTAL_ registros",
            "sInfoEmpty": "Mostrando 0 até 0 de 0 registros",
            "sInfoFiltered": "(filtrado de _MAX_ registros no total)",
            "sInfoPostFix": "",
            "sSearch": "Buscar:",
            "sUrl": "",
            "sInfoThousands": ".",
            "sLoadingRecords": "Carregando...",
            "oPaginate": {
                "sFirst": "Primeiro",
                "sLast": "Último",
                "sNext": "Próximo",
                "sPrevious": "Anterior"
            },
            "oAria": {
                "sSortAscending": ": Ordenar colunas de forma ascendente",
                "sSortDescending": ": Ordenar colunas de forma descendente"
            }
        }
    });
});