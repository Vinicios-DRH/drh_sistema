$('#formFiltros').on('submit', function(e) {
    e.preventDefault();
    var formData = $(this).serializeArray();
    var filters = {};

    formData.forEach(function(item) {
        filters[item.name] = item.value || null;  // Captura os filtros e garante que campos vazios sejam null

        // Verificação para ver o que está sendo capturado
        console.log("Filtro:", item.name, "=", item.value);
    });

    // Armazenar os filtros em cookies
    document.cookie = "filters=" + encodeURIComponent(JSON.stringify(filters)) + ";path=/";

    window.location.href = '/tabela-militares';
});
