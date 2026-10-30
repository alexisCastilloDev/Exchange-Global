<#import "template.ftl" as layout>
<#import "user-profile-commons.ftl" as userProfileCommons>
<#import "register-commons.ftl" as registerCommons>
<#--
Registro de usuario. Los campos salen del "user profile" declarativo del
realm, pero a propósito **no** se usa `userProfileCommons.userProfileFormFields`
(que renderiza absolutamente todos los atributos sin excepción, sin ningún
parámetro para excluir alguno): este registro de autoservicio solo pide
usuario y email; nombre/apellido se completan después, ya como cliente real,
no en este paso. El loop de abajo reproduce el mismo renderizado por atributo
que usa esa macro (ver user-profile-commons.ftl del tema "base" de Keycloak
26 — este tema hereda de "keycloak", que a su vez hereda de "base", nunca de
"keycloak.v2"; ambos definen la macro con una API distinta, no intercambiable),
omitiendo explícitamente firstName/lastName — si en el futuro se agrega
algún atributo nuevo al User Profile, aparece acá solo, sin tocar esto.
Las contraseñas van al final, después de todos los datos personales.
-->
<@layout.registrationLayout displayMessage=messagesPerField.exists('global') displayRequiredFields=false displayInfo=true; section>
    <#if section = "header">
        <#if messageHeader??>
            ${kcSanitize(msg("${messageHeader}"))?no_esc}
        <#else>
            ${msg("registerTitle")}
        </#if>
    <#elseif section = "form">
        <p class="ge-auth-card__subtitle">${msg("geRegisterSubtitle")}</p>

        <form id="kc-register-form" class="${properties.kcFormClass!} ge-form--register" action="${url.registrationAction}" method="post">

            <#assign currentGroup="">
            <#list profile.attributes as attribute>
                <#if attribute.name != 'firstName' && attribute.name != 'lastName'>
                    <#if attribute.name=='locale' && realm.internationalizationEnabled && locale.currentLanguageTag?has_content>
                        <input type="hidden" id="${attribute.name}" name="${attribute.name}" value="${locale.currentLanguageTag}"/>
                    <#else>
                        <#assign group = (attribute.group)!"">
                        <#if group != currentGroup>
                            <#assign currentGroup=group>
                            <#if currentGroup != "">
                                <div class="${properties.kcFormGroupClass!}"
                                <#list group.html5DataAnnotations as key, value>
                                    data-${key}="${value}"
                                </#list>
                                >
                                    <#assign groupDisplayHeader=group.displayHeader!"">
                                    <#if groupDisplayHeader != "">
                                        <#assign groupHeaderText=advancedMsg(groupDisplayHeader)!group>
                                    <#else>
                                        <#assign groupHeaderText=group.name!"">
                                    </#if>
                                    <div class="${properties.kcContentWrapperClass!}">
                                        <label id="header-${attribute.group.name}" class="${kcFormGroupHeader!}">${groupHeaderText}</label>
                                    </div>
                                    <#assign groupDisplayDescription=group.displayDescription!"">
                                    <#if groupDisplayDescription != "">
                                        <#assign groupDescriptionText=advancedMsg(groupDisplayDescription)!"">
                                        <div class="${properties.kcLabelWrapperClass!}">
                                            <label id="description-${group.name}" class="${properties.kcLabelClass!}">${groupDescriptionText}</label>
                                        </div>
                                    </#if>
                                </div>
                            </#if>
                        </#if>

                        <div class="${properties.kcFormGroupClass!}">
                            <div class="${properties.kcLabelWrapperClass!}">
                                <label for="${attribute.name}" class="${properties.kcLabelClass!}">${advancedMsg(attribute.displayName!'')}</label>
                                <#if attribute.required><span class="required">*</span></#if>
                            </div>
                            <div class="${properties.kcInputWrapperClass!}">
                                <#if attribute.annotations.inputHelperTextBefore??>
                                    <div class="${properties.kcInputHelperTextBeforeClass!}" id="form-help-text-before-${attribute.name}" aria-live="polite">${kcSanitize(advancedMsg(attribute.annotations.inputHelperTextBefore))?no_esc}</div>
                                </#if>
                                <@userProfileCommons.inputFieldByType attribute=attribute/>
                                <#if messagesPerField.existsError('${attribute.name}')>
                                    <span id="input-error-${attribute.name}" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                                        ${kcSanitize(messagesPerField.get('${attribute.name}'))?no_esc}
                                    </span>
                                </#if>
                                <#if attribute.annotations.inputHelperTextAfter??>
                                    <div class="${properties.kcInputHelperTextAfterClass!}" id="form-help-text-after-${attribute.name}" aria-live="polite">${kcSanitize(advancedMsg(attribute.annotations.inputHelperTextAfter))?no_esc}</div>
                                </#if>
                            </div>
                        </div>
                    </#if>
                </#if>
            </#list>

            <#if passwordRequired??>
                <div class="${properties.kcFormGroupClass!} ge-field--full">
                    <div class="${properties.kcLabelWrapperClass!}">
                        <label for="password" class="${properties.kcLabelClass!}">${msg("password")}</label>
                        <span class="required">*</span>
                    </div>
                    <div class="${properties.kcInputGroup!}" dir="ltr">
                        <input type="password" id="password" class="${properties.kcInputClass!}" name="password"
                               autocomplete="new-password"
                               aria-invalid="<#if messagesPerField.existsError('password','password-confirm')>true</#if>"
                        />
                        <button class="${properties.kcFormPasswordVisibilityButtonClass!}" type="button" aria-label="${msg('showPassword')}"
                                aria-controls="password" data-password-toggle
                                data-icon-show="${properties.kcFormPasswordVisibilityIconShow!}" data-icon-hide="${properties.kcFormPasswordVisibilityIconHide!}"
                                data-label-show="${msg('showPassword')}" data-label-hide="${msg('hidePassword')}">
                            <i class="${properties.kcFormPasswordVisibilityIconShow!}" aria-hidden="true"></i>
                        </button>
                    </div>
                    <#if messagesPerField.existsError('password')>
                        <span id="input-error-password" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                            ${kcSanitize(messagesPerField.get('password'))?no_esc}
                        </span>
                    </#if>
                </div>

                <div class="${properties.kcFormGroupClass!} ge-field--full">
                    <div class="${properties.kcLabelWrapperClass!}">
                        <label for="password-confirm" class="${properties.kcLabelClass!}">${msg("passwordConfirm")}</label>
                        <span class="required">*</span>
                    </div>
                    <div class="${properties.kcInputGroup!}" dir="ltr">
                        <input type="password" id="password-confirm" class="${properties.kcInputClass!}"
                               name="password-confirm" autocomplete="new-password"
                               aria-invalid="<#if messagesPerField.existsError('password-confirm')>true</#if>"
                        />
                        <button class="${properties.kcFormPasswordVisibilityButtonClass!}" type="button" aria-label="${msg('showPassword')}"
                                aria-controls="password-confirm" data-password-toggle
                                data-icon-show="${properties.kcFormPasswordVisibilityIconShow!}" data-icon-hide="${properties.kcFormPasswordVisibilityIconHide!}"
                                data-label-show="${msg('showPassword')}" data-label-hide="${msg('hidePassword')}">
                            <i class="${properties.kcFormPasswordVisibilityIconShow!}" aria-hidden="true"></i>
                        </button>
                    </div>
                    <#if messagesPerField.existsError('password-confirm')>
                        <span id="input-error-password-confirm" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                            ${kcSanitize(messagesPerField.get('password-confirm'))?no_esc}
                        </span>
                    </#if>
                </div>
            </#if>

            <div class="ge-field--full">
                <@registerCommons.termsAcceptance/>
            </div>

            <#if recaptchaRequired?? && (recaptchaVisible!false)>
                <div class="${properties.kcFormGroupClass!} ge-field--full">
                    <div class="g-recaptcha" data-size="compact" data-sitekey="${recaptchaSiteKey}" data-action="${recaptchaAction}"></div>
                </div>
            </#if>

            <div id="kc-form-buttons" class="${properties.kcFormButtonsClass!} ge-field--full">
                <#if recaptchaRequired?? && !(recaptchaVisible!false)>
                    <script>
                        function onSubmitRecaptcha(token) {
                            document.getElementById("kc-register-form").requestSubmit();
                        }
                    </script>
                    <button class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!} g-recaptcha"
                            data-sitekey="${recaptchaSiteKey}" data-callback="onSubmitRecaptcha" data-action="${recaptchaAction}" type="submit">
                        <i class="bi bi-person-plus" aria-hidden="true"></i> ${msg("doRegister")}
                    </button>
                <#else>
                    <button class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}" type="submit">
                        <i class="bi bi-person-plus" aria-hidden="true"></i> ${msg("doRegister")}
                    </button>
                </#if>
            </div>
        </form>
        <script type="module" src="${url.resourcesPath}/js/passwordVisibility.js"></script>
    <#elseif section = "info">
        <div id="kc-registration">
            <span>${msg("geHaveAccount")}</span>
            <a href="${url.loginUrl}">${msg("doLogIn")} <i class="bi bi-arrow-right" aria-hidden="true"></i></a>
        </div>
    </#if>
</@layout.registrationLayout>
