variable "api_image" {
  description = "Image de l'API (tag SHA ou digest, jamais latest)"
  type        = string
}

variable "db_user" {
  type    = string
  default = "app"
}

variable "db_name" {
  type    = string
  default = "tasks"
}

variable "db_password" {
  description = "Mot de passe PostgreSQL, à fournir via TF_VAR_db_password"
  type        = string
  sensitive   = true
}

variable "api_port" {
  type    = number
  default = 8001
}