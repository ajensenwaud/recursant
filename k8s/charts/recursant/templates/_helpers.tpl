{{/*
Expand the name of the chart.
*/}}
{{- define "recursant.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "recursant.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "recursant.labels" -}}
helm.sh/chart: {{ include "recursant.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: recursant
{{- end }}

{{/*
Selector labels for a specific component
*/}}
{{- define "recursant.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .release }}
{{- end }}

{{/*
Registry database URL
*/}}
{{- define "recursant.databaseUrl" -}}
postgresql://{{ .Values.secrets.dbUser }}:$(DB_PASSWORD)@{{ include "recursant.fullname" . }}-db:{{ .Values.db.port }}/{{ .Values.secrets.dbName }}
{{- end }}

{{/*
Redis URL — uses sentinel protocol when HA is enabled
*/}}
{{- define "recursant.redisUrl" -}}
{{- if .Values.redis.ha.enabled -}}
redis+sentinel://{{ include "recursant.fullname" . }}-redis-sentinel:26379/recursant-redis/0
{{- else -}}
redis://{{ include "recursant.fullname" . }}-redis:{{ .Values.redis.port }}/0
{{- end -}}
{{- end }}

{{/*
Namespace
*/}}
{{- define "recursant.namespace" -}}
{{- .Values.namespace | default "recursant" }}
{{- end }}

{{/*
Secret name
*/}}
{{- define "recursant.secretName" -}}
{{- include "recursant.fullname" . }}-secrets
{{- end }}

{{/*
Kafka bootstrap servers — empty string if Kafka is disabled
*/}}
{{- define "recursant.kafkaBootstrapServers" -}}
{{- if .Values.kafka.enabled -}}
{{- include "recursant.fullname" . }}-kafka:{{ .Values.kafka.port }}
{{- end -}}
{{- end }}
