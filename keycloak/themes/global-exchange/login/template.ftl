<#--
Layout común de todas las páginas de login del realm.
Replica el sistema de diseño del back-office de Django (static/css/style.css):
panel de marca en tinta (--ge-ink) a la izquierda, formulario en una
tarjeta con bordes (sin sombras) sobre fondo papel a la derecha.

Secciones que puede definir cada página:
  header           título de la tarjeta (obligatoria)
  show-username    contenido extra cuando se muestra el usuario ya ingresado
  form             cuerpo de la página
  socialProviders  botones de proveedores de identidad
  info             pie de la tarjeta (registrarse, volver, etc.)
-->
<#import "footer.ftl" as loginFooter>
<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false>
<!DOCTYPE html>
<html class="${properties.kcHtmlClass!}" lang="es"<#if realm.internationalizationEnabled> dir="${(locale.rtl)?then('rtl','ltr')}"</#if>>

<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="robots" content="noindex, nofollow">
    <#if properties.meta?has_content>
        <#list properties.meta?split(' ') as meta>
            <meta name="${meta?split('==')[0]}" content="${meta?split('==')[1]}"/>
        </#list>
    </#if>
    <title>${title!msg("loginTitle", (realm.displayName!'Global Exchange'))}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22><rect width=%2232%22 height=%2232%22 rx=%226%22 fill=%22%23B3812E%22/><text x=%2216%22 y=%2221%22 font-family=%22Arial,sans-serif%22 font-size=%2213%22 font-weight=%22800%22 text-anchor=%22middle%22 fill=%22%23101826%22>GE</text></svg>">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;650;700;800&display=swap" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
    <#if properties.styles?has_content>
        <#list properties.styles?split(' ') as style>
            <link href="${url.resourcesPath}/${style}" rel="stylesheet" />
        </#list>
    </#if>
    <#if properties.scripts?has_content>
        <#list properties.scripts?split(' ') as script>
            <script src="${url.resourcesPath}/${script}" type="text/javascript"></script>
        </#list>
    </#if>
    <script type="importmap">
        {
            "imports": {
                "rfc4648": "${url.resourcesCommonPath}/vendor/rfc4648/rfc4648.js"
            }
        }
    </script>
    <script src="${url.resourcesPath}/js/menu-button-links.js" type="module"></script>
    <#if scripts??>
        <#list scripts as script>
            <script src="${script}" type="text/javascript"></script>
        </#list>
    </#if>
    <script type="module">
        <#outputformat "JavaScript">
        import { startSessionPolling } from ${(url.resourcesPath + "/js/authChecker.js")?c};

        startSessionPolling(
            ${url.ssoLoginInOtherTabsUrl?c}
        );
        </#outputformat>
    </script>
    <script type="module">
        // Evita doble clic en enlaces de proveedores (comportamiento del tema base).
        document.addEventListener("click", (event) => {
            const link = event.target.closest("a[data-once-link]");
            if (!link) {
                return;
            }
            if (link.getAttribute("aria-disabled") === "true") {
                event.preventDefault();
                return;
            }
            const { disabledClass } = link.dataset;
            if (disabledClass) {
                link.classList.add(...disabledClass.trim().split(/\s+/));
            }
            link.setAttribute("role", "link");
            link.setAttribute("aria-disabled", "true");
        });
    </script>
    <#if authenticationSession??>
        <script type="module">
            <#outputformat "JavaScript">
            import { checkAuthSession } from ${(url.resourcesPath + "/js/authChecker.js")?c};

            checkAuthSession(
                ${authenticationSession.authSessionIdHash?c}
            );
            </#outputformat>
        </script>
    </#if>
</head>

<body class="${properties.kcBodyClass!} ${bodyClass}" data-page-id="login-${pageId!''}">
<div class="ge-auth">

    <#-- Panel de marca: mismo lenguaje visual que la landing pública (home.html) -->
    <aside class="ge-auth__brand" aria-hidden="true">
        <div class="ge-auth__brand-top">
            <span class="ge-brand-mark">GE</span>
            <span class="ge-brand-text">Global Exchange<small>Panel operativo</small></span>
        </div>

        <div class="ge-auth__brand-body">
            <h2>El panel operativo de tu casa de cambio</h2>
            <p>Gestioná clientes, cotizaciones y operaciones de tu equipo desde un mismo lugar.</p>

            <ul class="ge-ledger">
                <li>
                    <i class="bi bi-currency-exchange"></i>
                    <span><strong>Compra y venta de divisas</strong>Tasas vigentes y comisiones por segmento.</span>
                </li>
                <li>
                    <i class="bi bi-clock-history"></i>
                    <span><strong>Historial trazable</strong>Cada operación queda registrada con su detalle.</span>
                </li>
                <li>
                    <i class="bi bi-people"></i>
                    <span><strong>Accesos por rol</strong>Cada integrante ve solo lo que le corresponde.</span>
                </li>
            </ul>
        </div>

        <div class="ge-auth__brand-foot">
            <i class="bi bi-shield-lock"></i> Acceso protegido con Keycloak SSO
        </div>
    </aside>

    <main class="ge-auth__main">
        <div class="ge-auth__topbar">
            <span class="ge-auth__mobile-brand">
                <span class="ge-brand-mark">GE</span>
                Global Exchange
            </span>

            <#if realm.internationalizationEnabled && locale.supported?size gt 1>
                <div class="${properties.kcLocaleMainClass!}" id="kc-locale">
                    <div id="kc-locale-dropdown" class="menu-button-links">
                        <button tabindex="1" id="kc-current-locale-link" class="ge-locale__button" aria-label="${msg("languages")}" aria-haspopup="true" aria-expanded="false" aria-controls="language-switch1">
                            <i class="bi bi-translate" aria-hidden="true"></i> ${locale.current}
                        </button>
                        <ul role="menu" tabindex="-1" aria-labelledby="kc-current-locale-link" aria-activedescendant="" id="language-switch1" class="${properties.kcLocaleListClass!}">
                            <#assign i = 1>
                            <#list locale.supported as l>
                                <li role="none">
                                    <a role="menuitem" id="language-${i}" class="${properties.kcLocaleItemClass!}" href="${l.url}">${l.label}</a>
                                </li>
                                <#assign i++>
                            </#list>
                        </ul>
                    </div>
                </div>
            </#if>
        </div>

        <div class="ge-auth__center">
            <section class="ge-auth-card">
                <header class="ge-auth-card__header">
                    <h1 id="kc-page-title"><#nested "header"></h1>
                    <#if displayRequiredFields>
                        <p class="ge-auth-card__required"><span class="required">*</span> ${msg("requiredFields")}</p>
                    </#if>
                </header>

                <#if auth?has_content && auth.showUsername() && !auth.showResetCredentials()>
                    <#nested "show-username">
                    <div id="kc-username" class="ge-attempted-user">
                        <span class="ge-avatar"><i class="bi bi-person" aria-hidden="true"></i></span>
                        <label id="kc-attempted-username">${auth.attemptedUsername}</label>
                        <a id="reset-login" href="${url.loginRestartFlowUrl}" aria-label="${msg("restartLoginTooltip")}" title="${msg("restartLoginTooltip")}">
                            <i class="${properties.kcResetFlowIcon!}" aria-hidden="true"></i>
                            <span class="ge-sr-only">${msg("restartLoginTooltip")}</span>
                        </a>
                    </div>
                </#if>

                <#-- Las acciones iniciadas por la app no muestran avisos de "acción requerida" -->
                <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
                    <div class="${properties.kcAlertClass!} ge-alert--${message.type}" role="alert">
                        <#if message.type = 'success'><i class="${properties.kcFeedbackSuccessIcon!}" aria-hidden="true"></i></#if>
                        <#if message.type = 'warning'><i class="${properties.kcFeedbackWarningIcon!}" aria-hidden="true"></i></#if>
                        <#if message.type = 'error'><i class="${properties.kcFeedbackErrorIcon!}" aria-hidden="true"></i></#if>
                        <#if message.type = 'info'><i class="${properties.kcFeedbackInfoIcon!}" aria-hidden="true"></i></#if>
                        <span class="${properties.kcAlertTitleClass!}">${kcSanitize(message.summary)?no_esc}</span>
                    </div>
                </#if>

                <div id="kc-content">
                    <#nested "form">

                    <#if auth?has_content && auth.showTryAnotherWayLink()>
                        <form id="kc-select-try-another-way-form" action="${url.loginAction}" method="post" class="ge-try-another">
                            <input type="hidden" name="tryAnotherWay" value="on"/>
                            <a href="#" id="try-another-way"
                               onclick="document.forms['kc-select-try-another-way-form'].requestSubmit();return false;">${msg("doTryAnotherWay")}</a>
                        </form>
                    </#if>

                    <#if switchOrganizationEnabled?? && switchOrganizationEnabled>
                        <form id="kc-switch-organization-form" action="${url.loginAction}" method="post" class="ge-try-another">
                            <input type="hidden" name="switchOrganization" value="true"/>
                            <a href="#" id="switch-organization"
                               onclick="document.forms['kc-switch-organization-form'].requestSubmit();return false;">${msg("doSwitchOrganization")}</a>
                        </form>
                    </#if>

                    <#nested "socialProviders">
                </div>

                <#if displayInfo>
                    <div id="kc-info" class="${properties.kcSignUpClass!}">
                        <#nested "info">
                    </div>
                </#if>

                <@loginFooter.content/>
            </section>

            <p class="ge-auth__footnote">
                © Global Exchange · Casa de cambios
            </p>
        </div>
    </main>
</div>
</body>
</html>
</#macro>
