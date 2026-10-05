<#import "template.ftl" as layout>
<#--
Verificación de email pendiente. Aparece después de registrarse y cada vez
que alguien con el email sin verificar intenta iniciar sesión (con
"verifyEmail" activado en el realm). Volver a pedir esta página
(url.loginAction) reenvía el correo.
-->
<@layout.registrationLayout displayInfo=true; section>
    <#if section = "header">
        ${msg("emailVerifyTitle")}
    <#elseif section = "form">
        <div class="ge-icon-badge ge-icon-badge--teal"><i class="bi bi-envelope-check" aria-hidden="true"></i></div>

        <p class="ge-auth-card__subtitle">
            <#if verifyEmail??>
                ${msg("emailVerifyInstruction1", verifyEmail)}
            <#else>
                ${msg("emailVerifyInstruction4", user.email)}
            </#if>
        </p>

        <div class="ge-note">
            <i class="bi bi-info-circle" aria-hidden="true"></i>
            <span>${msg("geVerifyEmailHint")}</span>
        </div>

        <#if isAppInitiatedAction??>
            <form id="kc-verify-email-form" class="${properties.kcFormClass!}" action="${url.loginAction}" method="post">
                <div class="ge-btn-row">
                    <#if verifyEmail??>
                        <button class="${properties.kcButtonClass!} ${properties.kcButtonDefaultClass!} ${properties.kcButtonLargeClass!}" type="submit">${msg("emailVerifyResend")}</button>
                    <#else>
                        <button class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonLargeClass!}" type="submit">${msg("emailVerifySend")}</button>
                    </#if>
                    <button class="${properties.kcButtonClass!} ${properties.kcButtonDefaultClass!} ${properties.kcButtonLargeClass!}" type="submit" name="cancel-aia" value="true" formnovalidate>${msg("doCancel")}</button>
                </div>
            </form>
        <#else>
            <a id="kc-resend-email" class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}" href="${url.loginAction}">
                <i class="bi bi-arrow-repeat" aria-hidden="true"></i> ${msg("emailVerifyResend")}
            </a>
        </#if>
    <#elseif section = "info">
        <#if !isAppInitiatedAction??>
            <div id="kc-registration">
                <a href="${url.loginRestartFlowUrl}"><i class="bi bi-arrow-left" aria-hidden="true"></i> ${msg("geBackToLoginOtherAccount")}</a>
            </div>
        </#if>
    </#if>
</@layout.registrationLayout>
