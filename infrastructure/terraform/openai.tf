resource "azurerm_cognitive_deployment" "general" {
  name                   = local.azure_openai_chat_deployment_name
  cognitive_account_id   = data.azurerm_cognitive_account.openai.id
  version_upgrade_option = "NoAutoUpgrade"

  model {
    format  = "OpenAI"
    name    = "gpt-5-mini"
    version = "2025-08-07"
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.azure_openai_chat_capacity
  }
}

resource "azurerm_cognitive_deployment" "judge" {
  name                   = local.azure_openai_judge_deployment_name
  cognitive_account_id   = data.azurerm_cognitive_account.openai.id
  version_upgrade_option = "NoAutoUpgrade"

  model {
    format  = "OpenAI"
    name    = "gpt-5"
    version = "2025-08-07"
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.azure_openai_judge_capacity
  }
}
