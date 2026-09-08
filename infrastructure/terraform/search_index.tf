provider "azapi" {}

resource "azurerm_role_assignment" "search_index_admin" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Service Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azapi_data_plane_resource" "text_index" {
  type      = "Microsoft.Search/searchServices/indexes@2024-07-01"
  parent_id = "${azurerm_search_service.main.name}.search.windows.net"
  name      = "rag-text-chunks"

  body = {
    fields = [
      for field in [
        "id", "chunk_id", "document_id", "content", "source", "page"
        ] : {
        name        = field
        type        = field == "page" ? "Edm.Int32" : "Edm.String"
        key         = field == "id"
        searchable  = field == "content"
        filterable  = contains(["id", "document_id"], field)
        retrievable = true
      }
    ]
  }

  depends_on = [azurerm_role_assignment.search_index_admin]
}